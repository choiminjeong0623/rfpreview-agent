# Tasks

## 1. DB와 설정

- [x] 1.1 `ls db/migrations | tail -1`로 번호를 확인하고(다른 브랜치가 같은 번호를 쓰지 않는지도) `db/migrations/0047_session_auth.sql` 추가: `app_user`에 `login_id`(unique)·`password_hash`·`is_active`(기본 true), 기존 사용자 5명에 `engineer`·`approver`·`cost`·`quality`·`sales` 채움, `user_session`(token uuid PK, user_id, created_at, expires_at, revoked_at)과 user_id 색인. 확인: `rfp-db migrate`를 빈 DB와 기존 DB에서 두 번 돌려 오류 없음
- [x] 1.2 `RFP_SESSION_HOURS`(기본 8)·`RFP_COOKIE_SECURE`(기본 false)를 `config.py`·`.env.example`·`docker-compose.yml` 세 곳에 함께 추가. 확인: 설정 테스트에서 기본값과 환경 변수 값을 읽음

## 2. 비밀번호와 세션 (백엔드 `api/auth.py`)

- [x] 2.1 `hashlib.scrypt` 해시 함수(`scrypt$n$r$p$salt$hash`)와 `hmac.compare_digest` 대조, 없는 아이디는 더미 해시로 같은 시간 대조. 확인: 단위 테스트(맞음·틀림·형식 깨진 해시)
- [x] 2.2 `POST /api/auth/login`(아이디·비밀번호 → `user_session` 줄, 쿠키 `s2w_session` HttpOnly·SameSite=Lax·Secure는 설정), `POST /api/auth/logout`(`revoked_at`), `GET /api/auth/me`. 응답 모양은 `schemas.py`. 확인: pytest Scenario "맞는 비밀번호로 로그인", "틀린 비밀번호와 없는 아이디"(같은 401 문구), "비활성 사용자"
- [x] 2.3 `current_user` 의존성: 쿠키 없음·폐기·만료 세션은 401, 사용자 정보를 돌려줌. 확인: pytest Scenario "쿠키 없이 부르기", "로그아웃한 세션", "만료된 세션"

## 3. 모든 API에 로그인 걸기

- [x] 3.1 `runs`·`assistant`·`businesses`·`evaluation`·`reference`·`suggestions`·`prompts` 등 모든 라우터에 `current_user`를 라우터 단위로 걸고 `/api/health`·`/api/auth/login`만 공개. 확인: `test_every_route_requires_login`이 `app.routes`를 돌며 공개 목록 밖의 모든 경로가 쿠키 없이 401
- [x] 3.2 요청 스키마(`runs.py`·`prompts.py`·`suggestions.py`·`reference.py` 등)에서 `actor_id`·`user_id`를 지우고 동작·이력·권한을 세션 사용자로. `review.default_user` 대체는 API 층에서 쓰지 않음(CLI만). 확인: pytest Scenario "본문에 다른 사용자 번호"(이력은 로그인 엔지니어), "엔지니어가 승인 시도"(403), "지정 결재자 승인"
- [x] 3.3 `my_tasks`·`home/summary` 등 `user_id` 쿼리를 받던 조회를 세션 사용자로 바꿈. 확인: 다른 사용자 번호를 쿼리로 넣어도 내 것만 나오는 테스트
- [x] 3.4 파일 업로드(multipart) 요청은 `Origin`이 설정한 화면 주소와 다르면 403. 확인: pytest 한 건
- [x] 3.5 기존 pytest가 로그인 쿠키를 쓰도록 공통 fixture(`client_as(role)`) 추가·교체. 확인: 전체 pytest 통과(698 pass 기준, skip 수 그대로)
- [x] 3.6 `cd frontend && npm run gen:api`로 `openapi.json`·`src/api.gen.ts` 다시 만듦. 확인: `npm run check:api` 통과

## 4. 비밀번호 명령

- [x] 4.1 `rfp-db set-password <login_id>`(입력 숨김, 또는 `--stdin`)와 `rfp-db demo-setup --password`(시연 사용자 5명에 같은 비밀번호). 비밀번호 없는 사용자는 로그인 불가. 확인: CLI 테스트 두 건, 출력에 비밀번호가 나오지 않음

## 5. 화면

- [x] 5.1 `#/login`을 예시 화면에서 실제 로그인 화면으로: 틀리면 "아이디 또는 비밀번호가 맞지 않습니다.", 성공하면 `next` 주소로. 예시 화면 목록에서 로그인을 뺌. 확인: e2e Scenario "실제 로그인 화면"
- [x] 5.2 `shell/session.tsx`: `localStorage` `s2w.user` 대신 `GET /api/auth/me`, API 401이면 `#/login?next=<지금 주소>`, 머리글 사용자 바꾸기 겹창은 로그인한 사용자와 [로그아웃]·[다른 사용자로 로그인]. 확인: e2e Scenario "로그인한 사용자 보이기", "사용자 바꾸기", "로그아웃", "세션 없이 화면 열기"
- [x] 5.3 화면 API 호출에서 `actor_id`·`user_id`를 보내던 곳을 지움. 확인: `npm run lint`·`npm run build` 통과, 남은 `actor_id` grep 0
- [ ] 5.4 e2e `helpers.ts` `as()`를 `request.post('/api/auth/login')`(비밀번호 `E2E_PASSWORD`)로 바꿈. 확인: 기존 e2e를 로컬에서 돌려 통과·건너뛴 수 보고

## 6. 문서

- [x] 6.1 `docs/08-known-limits`(인증 없음 줄 고침), `docs/setup-guide.md`·`README.md`(첫 비밀번호 정하기), `docs/03` ADR-012(세션 방식 결정과 버린 대안). 확인: 적힌 명령을 그대로 돌려 로그인됨

## 7. 통합 확인

- [ ] 7.1 AGENTS.md 7장 검사 모두 통과: ruff, pytest(DB), `npm run lint`·`check:api`·`check:trace`·`build`, `openspec validate --all --strict`

## Workflow follow-up

- `npx --yes @fission-ai/openspec@1.14.3 archive add-session-auth --yes`
- AGENTS.md change 표에 다음 번호 줄(마이그레이션 0047)
- `cd frontend && npm run trace`
- PR 설명에 change 이름, 통과한 Scenario, 남은 `[확인 필요]`
- 커밋 뒤 `cd frontend && npm run sync-main -- --push`
