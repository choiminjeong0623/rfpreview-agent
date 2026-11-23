# Proposal

## Why

지금은 로그인이 예시 화면뿐이고, 서버는 쓰기 API 44개에서 요청 본문의 `actor_id`를 그대로 믿는다. `actor_id`를 비우면 기본 엔지니어로 처리한다(`review.default_user`). 그래서 승인자만 결재·운영 승격, 엔지니어만 단계부터 다시 같은 역할 검사는 업무 흐름 규칙일 뿐 보안 경계가 아니다(`docs/08-known-limits.md` 첫 줄). 포트폴리오 평가(2026-11-22)에서 가장 먼저 고칠 약점으로 꼽았고, 사용자가 방식으로 "비밀번호 + DB 세션"을 골랐다(11-23).

관련: FR-10(확인·승인·이력), AR(결재 승인 기준), CR-01(분기·권한 판단은 코드). SCR-00 앱 틀(머리글 사용자), SCR-01 로그인.

## What Changes

- 사용자마다 로그인 아이디·비밀번호를 두고, 서버가 로그인하면 세션을 만들어 쿠키로 준다. 로그아웃·만료·비활성 사용자는 세션을 잃는다.
- 상태 점검과 로그인 말고는 모든 API가 로그인을 요구한다(없으면 401).
- **BREAKING**: 쓰기 API는 요청 본문의 `actor_id`·`user_id`를 받지 않고 세션 사용자로 동작한다. "누가"를 기록하는 모든 이력도 세션 사용자다. 결재자(`approver_id`)처럼 "대상"을 고르는 칸은 그대로 둔다.
- 역할 검사는 지금 규칙(승인자만 결재·승격, 엔지니어만 단계부터 다시 등) 그대로, 입력만 세션 사용자로 바꾼다. 역할이 맞지 않으면 403.
- 화면: 예시 로그인 화면을 실제 로그인으로 바꾸고, 세션이 없으면 로그인 화면으로 보낸다. 머리글 "사용자 바꾸기"는 "다른 사용자로 로그인"(로그아웃 뒤 로그인)이 된다.
- 비밀번호는 명령(`rfp-db set-password`, `rfp-db demo-setup --password`)으로만 넣고 저장소에 두지 않는다.
- 마이그레이션 0047: 사용자 로그인 칸과 세션 표.

## Capabilities

### New Capabilities
- `user-auth`: 로그인·로그아웃·세션 만료, API 접근에 로그인 요구, 요청 값이 아닌 세션 사용자로 권한과 이력의 "누가"를 정하는 규칙

### Modified Capabilities
- `review-workspace`: "머리글 사용자 고르기" 요구사항을 로그인 기반으로 바꾼다(고른 사용자를 브라우저에 기억하지 않음, 로그아웃은 서버 세션을 끝냄)
- `review-run`: "검토 정보" 요구사항의 시작한 사람을 로그인한 사용자로 밝히고, "검토 정보 없이 시작"에서 담당 엔지니어는 시작한 엔지니어로 채워짐을 적는다(전에는 사용자 번호 없이 부르면 비어 있었음)

## Non-Goals

- 사내 SSO(OIDC)·다중 인자 인증·비밀번호 재설정 메일·사용자 관리 화면은 만들지 않는다. SSO는 `08-known-limits.md`의 다음 단계로 남긴다.
- 역할 체계(ENGINEER·COST·QUALITY·SALES·APPROVER)와 역할별 허용 동작은 바꾸지 않는다.
- 협조 요청 메일을 받는 부서 사람은 지금처럼 로그인하지 않는다.
- 배포·HTTPS 설정은 범위 밖(쿠키 Secure는 설정으로만 켬).

## Impact

- 백엔드: 새 `api/auth.py`(로그인·로그아웃·나), 공통 의존성(현재 사용자·역할 요구), `api/runs.py`·`suggestions.py`·`reference.py`·`prompts.py`·`businesses.py`·`evaluation.py`·`assistant.py` 전 라우터, `api/schemas.py`(요청 모델에서 `actor_id` 제거), `pipeline/review.py`(사용자 활성 확인), `db/cli.py`(`set-password`, `demo-setup --password`), `config.py`.
- DB: `db/migrations/0047_user_session.sql`.
- 설정(세 곳 함께): `RFP_SESSION_HOURS`, `RFP_COOKIE_SECURE`.
- 프런트: `shell/session.tsx`, 로그인 화면, `api.ts` 호출부(`actor_id` 제거), `openapi.json`·`src/api.gen.ts` 다시 만듦, e2e `helpers.ts`의 `as()`.
- 문서: `docs/08-known-limits.md`, `docs/setup.md`, `docs/03-adr.md`(ADR-012), README 실행하기.
