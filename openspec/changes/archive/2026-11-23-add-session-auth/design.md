# Design

## Context

- 쓰기 API 44개가 요청 본문의 `actor_id`(대부분 `int | None = None`)를 받고, 비면 `review.default_user(conn, "ENGINEER")`로 채운다. 읽기 API 중 `GET /runs/my-tasks?user_id=`, `GET /home/summary?user_id=`도 주소의 사용자 번호를 쓴다.
- 역할 검사는 이미 서버에서 DB 역할로 한다(`review._user_role`, `prompt_editor.EDIT_ROLES`·`PROMOTE_ROLES`, 결재자 지정 검사). 바뀌는 것은 "누구인지"의 출처뿐이다.
- 화면은 같은 출처(`/api`를 Vite 프록시)로 부르고, 고른 사용자를 `localStorage`의 `s2w.user`에 둔다. 로그인 화면(`#/login`)은 예시다.
- 테스트 대부분은 파이프라인 함수를 직접 부르고 사용자 번호를 인자로 넘긴다. API(`TestClient`)를 쓰는 테스트는 일부다.
- 앱 사용자는 6명(기본 엔지니어·승인자·견적·품질·영업 등, 마이그레이션 0003·0005·0008이 넣음). 운영 배포는 없고 로컬 Docker Compose만 있다.

## Goals / Non-Goals

**Goals:**
- 요청 값으로 다른 사용자가 될 수 없게 한다. 앞으로 API를 더해도 로그인 요구가 빠지지 않게 시험으로 막는다.
- 새 의존성 없이 지금 스택(FastAPI·PostgreSQL)으로 끝낸다.
- 파이프라인 함수의 인자 모양은 바꾸지 않는다(CLI·시험이 그대로 씀).

**Non-Goals:**
- SSO, 비밀번호 정책·잠금, 사용자 관리 화면, 세션 목록 화면.

## Decisions

1. **DB 세션 표 + 임의 토큰 쿠키** (대안: 서명 쿠키·JWT)
   - `user_session(token uuid PK, user_id, created_at, expires_at, revoked_at)`. 쿠키에는 토큰만 둔다.
   - 이유: 로그아웃·비활성화가 즉시 효력을 갖고, 서명 비밀값을 따로 관리·회전할 필요가 없으며, 이미 모든 상태를 PostgreSQL에 두는 구조와 맞다. 요청마다 조회 한 번이 들지만 사용자 수가 작아 문제가 없다.
   - JWT는 만료 전 강제 종료가 어렵고, 서명 쿠키는 비밀값 설정이 하나 더 는다.
2. **비밀번호 해시: 표준 라이브러리 `hashlib.scrypt`** (대안: argon2·bcrypt 패키지)
   - 형식 `scrypt$n$r$p$salt$hash`로 저장해 나중에 매개변수를 바꿔도 예전 해시를 읽는다. 비교는 `hmac.compare_digest`.
   - 없는 아이디에도 같은 해시 계산을 한 번 해 응답 시간으로 아이디 유무를 알 수 없게 한다.
3. **공통 의존성 `current_user`를 라우터 단위로 건다**
   - `APIRouter(dependencies=...)`로 라우터 전체에 걸고, 공개 경로(`/api/health`, `/api/auth/login`)만 별도 라우터에 둔다. 각 라우트 함수는 사용자가 필요하면 `user: CurrentUser`로 받는다.
   - 시험 `test_every_route_requires_login`이 `app.routes`를 돌며 공개 목록 밖 경로가 쿠키 없이 401인지 본다. 새 라우터에 의존성을 잊으면 시험이 실패한다.
4. **요청 모델에서 `actor_id`·`user_id`를 지운다** (대안: 받되 무시)
   - 스키마가 진실이 되도록 지우고 `npm run gen:api`로 화면 타입에서도 사라지게 한다. Pydantic 기본 설정이 모르는 칸을 무시하므로 옛 화면이 보내도 오류는 나지 않고 값은 쓰이지 않는다(시나리오 "본문에 다른 사용자 번호").
   - API 층에서 `default_user` 대체를 쓰지 않는다. 파이프라인의 `default_user`는 CLI용으로 남긴다.
5. **CSRF는 SameSite=Lax + 같은 출처 확인**
   - 상태를 바꾸는 요청(GET·HEAD·OPTIONS 밖, 로그인 포함)은 `Origin`(없으면 `Referer`)의 호스트가 요청 호스트와 다르면 403. 업로드(multipart)는 브라우저가 교차 출처로 보낼 수 있어서이고, JSON 요청도 같은 검사를 건다(추가 비용 없음). Origin·Referer가 모두 없으면 브라우저가 아닌 요청이라 통과한다.
   - 프록시 뒤에서는 `X-Forwarded-Host`를 요청 호스트로 본다. Vite 개발 서버 프록시는 `changeOrigin`으로 Host를 백엔드 주소로 바꾸므로 `xfwd: true`로 원래 주소를 넘긴다(구현 중 e2e에서 로그인이 403으로 막혀 찾음). 이 머리는 교차 출처 브라우저가 사전 확인 없이 보낼 수 없어 CSRF 검사에 써도 된다.
6. **세션 유지와 쿠키 설정**
   - `RFP_SESSION_HOURS`(기본 8, 마지막 요청 기준 아님·고정 만료), `RFP_COOKIE_SECURE`(기본 false, 배포 시 true). 쿠키 이름 `s2w_session`, `HttpOnly`, `SameSite=Lax`, `Path=/`.
7. **비밀번호 넣기는 명령으로만**
   - `rfp-db set-password --login <id>`(입력 숨김 프롬프트 또는 `--password-stdin`), `rfp-db demo-setup --password <값>`은 시연 사용자 모두에 같은 비밀번호. 로그인 아이디는 마이그레이션이 기존 사용자에 `engineer`·`approver`·`cost`·`quality`·`sales` 식으로 채우고, 비밀번호가 없는 사용자는 로그인할 수 없다.
8. **화면**
   - `SessionProvider`는 `/auth/me`로 사용자를 읽고, API 응답 401을 받으면 `#/login?next=<주소>`로 보낸다. `localStorage`의 `s2w.user`는 지운다.
   - 로그인 화면은 지금 예시 레이아웃을 그대로 쓰고 입력칸·오류 문구만 실제로 잇는다.
   - e2e `as(page, userId)`는 `page.request.post('/api/auth/login')`로 쿠키를 받아 페이지 문맥에 넣는다. 시연 비밀번호는 환경 변수 `E2E_PASSWORD`(기본 `demo-pass-1`). 시작할 때 `e2e/global-setup.ts`가 엔지니어로 로그인한 쿠키를 저장해(`use.storageState`) 모든 시험이 엔지니어로 시작하고, 승인자 결정처럼 API로 다른 사용자가 할 일은 `asLogin(request, 'approver', fn)`. 백엔드를 흉내 내는 시험은 `mockMe(page, id)`로 `/api/auth/me`를 정한다.
9. **pytest**
   - API 시험 대부분은 로그인 뒤 동작을 보므로 `conftest.logged_in`(autouse)이 `current_user`를 바꿔 끼워 머리 `X-Test-User`(사용자 번호)의 사용자, 없으면 기본 엔지니어로 둔다. 본문 `actor_id`로 사용자를 바꾸던 시험은 이 머리로 바꿨다.
   - 로그인·세션 시나리오와 경로 시험은 `@pytest.mark.real_auth`로 바꿔 끼우지 않고 실제 쿠키로 돈다(`tests/test_session_auth.py`).
   - 사용자 번호 없이 시작하면 담당 엔지니어가 비던 시나리오("검토 정보 없이 시작")는 이제 시작한 엔지니어가 담당이 된다. 기존 규칙("시작한 사람이 엔지니어면 담당")이 그대로 적용된 결과라 `review-run` 스펙 delta로 문장을 맞췄다.

## Risks / Trade-offs

- [화면 호출부 138곳을 고치다 빠뜨림] → 스키마에서 칸을 지우면 `tsc`(`npm run build`)가 남은 곳을 잡는다.
- [로컬 e2e 57개가 한꺼번에 영향] → 로그인을 `as()` 한 곳에서 처리, 핵심 흐름부터 통과 확인.
- [시연 영상과 화면이 달라짐] → 로그인 장면만 다시 찍기(선택), 문서에 표시.
- [세션 조회가 요청마다 DB를 한 번 더 부름] → 기본 키 조회 1회. 지금 규모에서는 측정할 만한 비용 아님.
- [기존 DB에 비밀번호가 없어 아무도 로그인 못 함] → 마이그레이션 뒤 `set-password` 안내를 `setup.md`와 시작 로그 경고로.

## Migration Plan

1. 0047 적용(로그인 아이디 채움, `password_hash` 비움, 세션 표 생성).
2. `rfp-db set-password` 또는 `demo-setup --password`로 비밀번호 넣기.
3. 되돌리기: 이 change 전 커밋으로 돌아가면 새 칸·표는 쓰이지 않을 뿐 옛 코드가 동작한다(칸 추가만, 기존 칸 변경 없음).
