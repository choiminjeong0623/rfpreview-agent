"""로그인·로그아웃과 로그인 요구 의존성 (add-session-auth, 명세 user-auth).

모든 라우터는 `dependencies=LOGIN`으로 로그인을 요구하고, 사용자가 필요한 라우트는
`user: CurrentUser`로 받는다. 공개 경로는 `/api/health`와 `/api/auth/login`뿐이다
(`tests/test_session_auth.py::test_every_route_requires_login`이 지킨다).
"""
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from rfp_agent import auth
from rfp_agent.api.schemas import SessionUser
from rfp_agent.config import get_settings
from rfp_agent.db.connection import connect

BAD_LOGIN = "아이디 또는 비밀번호가 맞지 않습니다."
NO_LOGIN = "로그인이 필요합니다."
SAFE = {"GET", "HEAD", "OPTIONS"}


def _same_origin(request: Request) -> bool:
    """상태를 바꾸는 요청은 같은 출처에서만.

    Origin(없으면 Referer)이 없으면 브라우저가 보낸 요청이 아니므로 통과한다."""
    sent = request.headers.get("origin") or request.headers.get("referer")
    if not sent:
        return True
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    return urlsplit(sent).netloc == host


def current_user(request: Request) -> auth.User:
    """쿠키의 세션으로 사용자를 찾는다. 없거나 끝난 세션이면 401. 한 요청에 한 번만 조회한다."""
    if request.method not in SAFE and not _same_origin(request):
        raise HTTPException(403, "다른 사이트에서 보낸 요청은 받지 않습니다.")
    token = request.cookies.get(auth.COOKIE)
    user = None
    if token:
        with connect() as conn:
            user = auth.session_user(conn, token)
    if user is None:
        raise HTTPException(401, NO_LOGIN)
    return user


CurrentUser = Annotated[auth.User, Depends(current_user)]
LOGIN = [Depends(current_user)]

public = APIRouter(prefix="/api/auth", tags=["로그인"])
router = APIRouter(prefix="/api/auth", tags=["로그인"], dependencies=LOGIN)


class LoginBody(BaseModel):
    login_id: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=1, max_length=200)


def _out(user: auth.User) -> SessionUser:
    return SessionUser(user_id=user.user_id, user_name=user.user_name, role=user.role,
                       login_id=user.login_id)


@public.post("/login")
def login(body: LoginBody, request: Request, response: Response) -> SessionUser:
    """아이디·비밀번호가 맞으면 세션 쿠키를 준다. 틀린 비밀번호·없는 아이디·비활성은 같은 401."""
    if not _same_origin(request):
        raise HTTPException(403, "다른 사이트에서 보낸 요청은 받지 않습니다.")
    settings = get_settings()
    with connect() as conn:
        got = auth.login(conn, body.login_id, body.password, settings.rfp_session_hours)
    if got is None:
        raise HTTPException(401, BAD_LOGIN)
    user, token = got
    response.set_cookie(auth.COOKIE, token, max_age=settings.rfp_session_hours * 3600,
                        httponly=True, samesite="lax", secure=settings.rfp_cookie_secure, path="/")
    return _out(user)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response) -> None:
    """서버 세션을 끝내고 쿠키를 지운다."""
    with connect() as conn:
        auth.logout(conn, request.cookies.get(auth.COOKIE))
    response.delete_cookie(auth.COOKIE, path="/")


@router.get("/me")
def me(user: CurrentUser) -> SessionUser:
    return _out(user)
