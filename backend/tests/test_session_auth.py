"""로그인과 세션 (change add-session-auth, 명세 user-auth).

이 파일의 API 시험은 시험용 로그인 바꿔 끼우기 없이(`real_auth`) 실제 쿠키·세션으로 돈다.
"""
import io
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from rfp_agent import auth
from rfp_agent.api.auth import BAD_LOGIN
from rfp_agent.api.main import app
from rfp_agent.db import cli
from rfp_agent.pipeline import review
from rfp_agent.pipeline.run import RunContext, create_run, execute_run

PASSWORD = "demo-pass-1"
VERSION = "test-dict-v1"
PUBLIC = {("GET", "/api/health"), ("POST", "/api/auth/login")}


# ── 비밀번호 해시 (DB 없이) ──────────────────────────────────────

def test_hash_and_verify():
    stored = auth.hash_password("abc12345")
    assert stored.startswith("scrypt$16384$8$1$") and "abc12345" not in stored
    assert auth.verify_password("abc12345", stored)
    assert not auth.verify_password("abc12346", stored)
    assert auth.hash_password("abc12345") != stored          # 소금이 매번 다름


@pytest.mark.parametrize("broken", [None, "", "plain", "scrypt$1$2", "bcrypt$a$b$c$d$e",
                                    "scrypt$x$8$1$AA==$AA=="])
def test_broken_hash_is_refused(broken):
    assert auth.verify_password("abc12345", broken) is False


@pytest.mark.real_auth
def test_every_route_requires_login():
    """앞으로 API를 더해도 로그인 요구가 빠지지 않게: 공개 목록 밖 경로는 모두 쿠키 없이 401."""
    client = TestClient(app)
    checked = 0
    # 모든 API는 스키마(/openapi.json)에 실린다 (include_in_schema=False 없음)
    for route, ops in app.openapi()["paths"].items():
        path = route.replace("{group}", "x")
        for key in ("run_id", "file_no", "requirement_id", "loss_calc_id", "assignment_id",
                    "business_id", "other_id", "suggestion_id", "candidate_id", "eval_id",
                    "row_id", "key", "code", "role", "dictionary"):
            path = path.replace("{" + key + "}", "1")
        assert "{" not in path, f"시험이 모르는 경로 변수: {route}"
        for method in ops:
            if (method.upper(), route) in PUBLIC:
                continue
            res = client.request(method.upper(), path)
            assert res.status_code == 401, f"{method} {route}: {res.status_code}"
            checked += 1
    assert checked > 100


# ── 실제 쿠키·세션 (DB) ──────────────────────────────────────────

@pytest.fixture
def client(seeded_db, db_url, monkeypatch):
    from rfp_agent.config import get_settings

    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    get_settings.cache_clear()
    for login_id in ("engineer", "approver"):
        auth.set_password(seeded_db, login_id, PASSWORD)
    seeded_db.commit()
    yield TestClient(app)
    get_settings.cache_clear()


def login(client, login_id="engineer", password=PASSWORD):
    return client.post("/api/auth/login", json={"login_id": login_id, "password": password})


def test_migration_gives_login_ids(seeded_db):
    rows = dict(seeded_db.execute("SELECT login_id, role FROM app_user WHERE login_id IS NOT NULL"
                                  ).fetchall())
    assert rows == {"engineer": "ENGINEER", "approver": "APPROVER", "cost": "COST",
                    "quality": "QUALITY", "sales": "SALES"}


@pytest.mark.real_auth
def test_login_with_right_password(client):
    """Scenario: 맞는 비밀번호로 로그인 — 세션 쿠키, /me가 그 사용자."""
    res = login(client)
    assert res.status_code == 200
    assert res.json() == {"user_id": res.json()["user_id"], "user_name": "기본 엔지니어",
                          "role": "ENGINEER", "login_id": "engineer"}
    cookie = res.headers["set-cookie"].lower()
    assert "s2w_session=" in cookie and "httponly" in cookie and "samesite=lax" in cookie
    assert client.get("/api/auth/me").json()["login_id"] == "engineer"
    assert client.get("/api/runs").status_code == 200


@pytest.mark.real_auth
def test_wrong_password_and_unknown_id(client):
    """Scenario: 틀린 비밀번호와 없는 아이디 — 같은 401 문구, 쿠키 없음."""
    wrong, unknown = login(client, password="wrong-pass"), login(client, "nobody")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"detail": BAD_LOGIN}
    assert "set-cookie" not in wrong.headers and "set-cookie" not in unknown.headers
    assert login(client, "cost").status_code == 401         # 비밀번호를 정하지 않은 사용자


@pytest.mark.real_auth
def test_inactive_user(client, seeded_db):
    """Scenario: 비활성 사용자 — 맞는 비밀번호여도 401, 살아 있던 세션도 끝."""
    assert login(client).status_code == 200
    seeded_db.execute("UPDATE app_user SET is_active = false WHERE login_id = 'engineer'")
    seeded_db.commit()
    assert client.get("/api/runs").status_code == 401
    assert login(client).json() == {"detail": BAD_LOGIN}


@pytest.mark.real_auth
def test_no_cookie(client):
    """Scenario: 쿠키 없이 부르기 — 401 "로그인이 필요합니다."."""
    res = client.get("/api/runs")
    assert res.status_code == 401 and res.json()["detail"] == "로그인이 필요합니다."
    assert client.get("/api/health").status_code == 200


@pytest.mark.real_auth
def test_logged_out_session(client):
    """Scenario: 로그아웃한 세션 — 같은 토큰을 다시 보내도 401."""
    login(client)
    token = client.cookies.get(auth.COOKIE)
    assert client.post("/api/auth/logout").status_code == 204
    client.cookies.set(auth.COOKIE, token)
    assert client.get("/api/runs").status_code == 401


@pytest.mark.real_auth
def test_expired_session(client, seeded_db):
    """Scenario: 만료된 세션 — 만료 시각이 지나면 401."""
    login(client)
    seeded_db.execute("UPDATE user_session SET expires_at = now() - %s", (timedelta(minutes=1),))
    seeded_db.commit()
    assert client.get("/api/runs").status_code == 401


@pytest.mark.real_auth
def test_other_site_upload_refused(client):
    """다른 출처에서 보낸 쓰기 요청은 로그인 쿠키가 있어도 403 (CSRF)."""
    login(client)
    res = client.post("/api/runs", files=[("files", ("a.docx", b"x"))],
                      headers={"Origin": "https://evil.example"})
    assert res.status_code == 403
    # 화면 개발 서버 프록시 뒤: 원래 주소(X-Forwarded-Host)가 Origin과 같으면 같은 출처
    res = client.post("/api/auth/logout", headers={"Origin": "http://localhost:5173",
                                                   "X-Forwarded-Host": "localhost:5173"})
    assert res.status_code == 204


@pytest.fixture
def run(db, spec):
    run_id = create_run(db, VERSION, None)
    assert execute_run(RunContext(db, VERSION, None, None), run_id, [spec]) == "ENGINEER_REVIEW"
    return run_id


@pytest.mark.real_auth
def test_engineer_tries_approval(run, client, db):
    """Scenario: 엔지니어가 승인 시도 — 본문에 승인자 번호를 넣어도 403, 단계 그대로."""
    approver = review.default_user(db, "APPROVER")
    login(client)
    base = f"/api/runs/{run}"
    assert client.post(f"{base}/finish-review", json={"approver_id": approver,
                                                      "comment": "확인 부탁"}).status_code == 200
    res = client.post(f"{base}/approval", json={"decision": "APPROVED", "actor_id": approver})
    assert res.status_code == 403
    assert client.get(base).json()["stage"] == "APPROVAL"


@pytest.mark.real_auth
def test_body_user_is_ignored(run, client, db):
    """Scenario: 본문에 다른 사용자 번호 — 이력은 로그인한 엔지니어."""
    approver = review.default_user(db, "APPROVER")
    login(client)
    judgment = client.get(f"/api/runs/{run}/judgments").json()[0]
    res = client.post(f"/api/runs/{run}/actions", json={
        "target": "judgment", "target_id": judgment["judgment_id"], "action": "CONFIRM",
        "actor_id": approver})
    assert res.status_code == 200
    [log] = [h for h in client.get(f"/api/runs/{run}/history").json()
             if h["target_table"] == "judgment" and h["target_id"] == judgment["judgment_id"]
             and h["action"] == "CONFIRM"]
    assert log["actor"] == "기본 엔지니어"


@pytest.mark.real_auth
def test_designated_approver_approves(run, client, db):
    """Scenario: 지정 결재자 승인 — 결재자로 로그인해 승인하면 이력의 결정자가 그 사람."""
    approver = review.default_user(db, "APPROVER")
    login(client)
    base = f"/api/runs/{run}"
    client.post(f"{base}/finish-review", json={"approver_id": approver, "comment": "확인"})
    client.post("/api/auth/logout")
    login(client, "approver")
    res = client.post(f"{base}/approval", json={"decision": "APPROVED"})
    assert res.status_code == 200, res.text
    assert client.get(base).json()["stage"] == "APPROVED"
    decided = [h for h in client.get(f"{base}/history").json()
               if h["target_table"] == "review_run" and h["action"] == "CONFIRM"
               and h["before_value"] == {"stage": "APPROVAL"}]
    assert [h["actor"] for h in decided] == ["기본 승인자"]


# ── 비밀번호 명령 ─────────────────────────────────────────────

@pytest.fixture
def env(db_url, monkeypatch):
    from rfp_agent.config import get_settings

    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_set_password_command(seeded_db, env, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("new-secret-9\n"))
    cli.main(["set-password", "--login", "approver", "--password-stdin"])
    out = capsys.readouterr().out
    assert "approver" in out and "new-secret-9" not in out
    seeded_db.rollback()
    got = auth.login(seeded_db, "approver", "new-secret-9", 1)
    assert got is not None and got[0].role == "APPROVER"
    monkeypatch.setattr("sys.stdin", io.StringIO("short\n"))
    with pytest.raises(SystemExit, match="8자 이상"):
        cli.main(["set-password", "--login", "approver", "--password-stdin"])
    monkeypatch.setattr("sys.stdin", io.StringIO("long-enough-1\n"))
    with pytest.raises(SystemExit, match="없습니다"):
        cli.main(["set-password", "--login", "nobody", "--password-stdin"])


def test_set_password_ends_sessions(seeded_db):
    auth.set_password(seeded_db, "engineer", PASSWORD)
    _, token = auth.login(seeded_db, "engineer", PASSWORD, 1)
    assert auth.session_user(seeded_db, token) is not None
    auth.set_password(seeded_db, "engineer", "another-pass")
    assert auth.session_user(seeded_db, token) is None


def test_session_settings(monkeypatch):
    """로그인 세션 설정 (RFP_SESSION_HOURS 기본 8, RFP_COOKIE_SECURE 기본 false)."""
    from rfp_agent.config import Settings

    monkeypatch.delenv("RFP_SESSION_HOURS", raising=False)
    monkeypatch.delenv("RFP_COOKIE_SECURE", raising=False)
    default = Settings(_env_file=None)
    assert (default.rfp_session_hours, default.rfp_cookie_secure) == (8, False)
    monkeypatch.setenv("RFP_SESSION_HOURS", "2")
    monkeypatch.setenv("RFP_COOKIE_SECURE", "true")
    changed = Settings(_env_file=None)
    assert (changed.rfp_session_hours, changed.rfp_cookie_secure) == (2, True)


@pytest.mark.real_auth
def test_secure_cookie_setting(client, monkeypatch):
    from rfp_agent.config import get_settings

    monkeypatch.setenv("RFP_COOKIE_SECURE", "true")
    get_settings.cache_clear()
    assert "secure" in login(client).headers["set-cookie"].lower()
