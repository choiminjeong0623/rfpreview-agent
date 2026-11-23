"""로그인과 세션 (add-session-auth). API·CLI가 함께 쓴다.

비밀번호는 표준 라이브러리 scrypt로 `scrypt$n$r$p$salt$hash` 모양으로 저장한다(매개변수를 바꿔도
예전 해시를 읽음). 세션은 DB 표 `user_session`의 임의 토큰이고, 쿠키에는 토큰만 둔다.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import timedelta

import psycopg

N, R, P = 2 ** 14, 8, 1
COOKIE = "s2w_session"
MIN_PASSWORD = 8


@dataclass(frozen=True)
class User:
    user_id: int
    user_name: str
    role: str
    login_id: str | None


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=N, r=R, p=P, dklen=32)
    return f"scrypt${N}${R}${P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str | None) -> bool:
    """저장된 해시와 대조한다. 형식이 깨졌거나 비어 있으면 False."""
    try:
        kind, n, r, p, salt, digest = (stored or "").split("$")
        if kind != "scrypt":
            return False
        want = base64.b64decode(digest)
        got = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r),
                             p=int(p), dklen=len(want))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(got, want)


# 없는 아이디에도 같은 계산을 한 번 해 응답 시간으로 아이디 유무를 알 수 없게 한다
_DUMMY = hash_password("not-a-password", salt=b"\0" * 16)


def login(conn: psycopg.Connection, login_id: str, password: str,
          hours: int) -> tuple[User, str] | None:
    """아이디·비밀번호가 맞고 활성 사용자면 (사용자, 세션 토큰). 아니면 None (이유 구분 없음)."""
    row = conn.execute("SELECT user_id, user_name, role, login_id, password_hash, is_active "
                       "FROM app_user WHERE login_id = %s", (login_id.strip(),)).fetchone()
    ok = verify_password(password, row[4] if row and row[4] else _DUMMY)
    if row is None or not row[4] or not ok or not row[5]:
        return None
    token = uuid.uuid4()
    conn.execute("INSERT INTO user_session (token, user_id, expires_at) "
                 "VALUES (%s, %s, now() + %s)", (token, row[0], timedelta(hours=hours)))
    return User(row[0], row[1], row[2], row[3]), str(token)


def session_user(conn: psycopg.Connection, token: str | None) -> User | None:
    """살아 있는 세션의 사용자. 토큰이 없거나·폐기·만료·비활성이면 None."""
    try:
        key = uuid.UUID(token or "")
    except ValueError:
        return None
    row = conn.execute(
        "SELECT u.user_id, u.user_name, u.role, u.login_id FROM user_session s "
        "JOIN app_user u USING (user_id) WHERE s.token = %s AND s.revoked_at IS NULL "
        "AND s.expires_at > now() AND u.is_active", (key,)).fetchone()
    return User(*row) if row else None


def logout(conn: psycopg.Connection, token: str | None) -> None:
    try:
        key = uuid.UUID(token or "")
    except ValueError:
        return
    conn.execute("UPDATE user_session SET revoked_at = now() WHERE token = %s "
                 "AND revoked_at IS NULL", (key,))


def set_password(conn: psycopg.Connection, login_id: str, password: str) -> int:
    """비밀번호를 정하고 그 사용자의 살아 있는 세션을 끝낸다. 사용자 번호를 돌려준다."""
    if len(password) < MIN_PASSWORD:
        raise ValueError(f"비밀번호는 {MIN_PASSWORD}자 이상이어야 합니다.")
    row = conn.execute("UPDATE app_user SET password_hash = %s WHERE login_id = %s "
                       "RETURNING user_id", (hash_password(password), login_id)).fetchone()
    if row is None:
        raise LookupError(f"로그인 아이디 {login_id}이(가) 없습니다.")
    conn.execute("UPDATE user_session SET revoked_at = now() WHERE user_id = %s "
                 "AND revoked_at IS NULL", (row[0],))
    return row[0]
