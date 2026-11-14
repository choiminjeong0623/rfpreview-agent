@AGENTS.md

## Claude Code 전용

### OpenSpec
- 명령: `/opsx:propose`(change 만들기), `/opsx:apply <change>`(구현), `/opsx:archive <change>`(마무리), `/opsx:explore`(조사).
- `/opsx:propose`는 계획만 만든다. 구현은 사람이 확인한 뒤 `/opsx:apply`로 시작한다.
- CLI는 CI와 같은 판을 쓴다: `npx --yes @fission-ai/openspec@1.14.3 <명령>`. `@latest`는 `openspec/config.yaml`을 읽지 못한다.

### 처리 흐름 (`pipeline/run.py` `build_graph`)
- 검토 하나 = LangGraph 흐름 하나(thread `run-<run_id>`). 단계마다 흐름 상태를 PostgreSQL에 저장(checkpoint)한다.
- 등록: 파일을 올리면 분석 전에 문서 종류·묶음을 추천하고, 사람이 확인·수정한 뒤 시작한다.
- 처리 단계(`PIPELINE`, 일직선): `documents`(문서마다 읽기 → 분류 → 절·표 나누기 → 요구사항 추출 → 유형 → 값 정리) → `pairs`(원본·정정본 쌍 후보) → `risks`(위험 조건 후보) → `judge`(제품 비교 판정) → `meaning`(문장 벡터, 후보·힌트만) → `check`(공학 검산) → `warranty`(보증값 후보) → `loss`(손실 환산) → `outputs`(일탈·질의 초안) → `proposals`(제안 포인트 후보) → `assign`(협조 요청 만들기).
- 멈춤 자리(`STOPS`): 처리가 끝나면 `engineer_review`(담당자 확인)에서, 상신하면 `approval`(승인 대기)에서, 반려되면 `rejected`에서 `interrupt`로 실제로 멈춘다. 사람 동작 없이는 다음으로 가지 않는다.
- 멈춘 뒤 갈 곳은 `NEXT` 표로 코드가 고른다(CR-01): 담당자 확인 → 상신·문서 추가·단계부터 다시(rewind), 승인 대기 → 승인(끝)·반려·상신 취소, 반려됨 → 다시 확인.
- 새 처리 단계·멈춤 자리를 더하면 `PIPELINE`·`STOPS`·`NEXT`와 흐름 기록(`graph_flow`)을 함께 본다.

### 코드 지도 (`backend/src/rfp_agent/`)
- `api/`: FastAPI 라우터(`runs`, `assistant`, `businesses`, `evaluation`, `reference`, `suggestions`, `main`의 `/api/health`). 응답 모양은 `schemas.py`.
- `llm/`: 언어 모델 호출은 여기서만(`client` Gemini·사내 호출·재시도·오류 종류, `tasks` 프롬프트·답 형식, `evidence` 근거 대조, `parallel` 동시 호출).
- `pipeline/`: 처리 단계, 흐름(`run.py`·`graph_flow.py`), 사람 동작(`review.py` 등), 화면용 조회. 단계마다 파일이 따로 있다.
- `db/`: `rfp-db` CLI(`migrate`, `seed-rules`, `seed-products` 등), 마이그레이션 실행(파일 이름 순서로 한 번씩), 연결.
- `notify/`: SMTP 메일 발송(`mail.py`)만. 테스트는 `set_mailer(FakeMailer(...))`.

### 세션을 시작할 때
- `git status`, `git branch --show-current`, `openspec list`로 진행 중인 change와 커밋 안 한 변경부터 본다. 남이 작업 중인 폴더에서는 브랜치를 바꾸거나 커밋하지 않는다.
- 무엇을 기준으로 볼지는 셋으로 나눈다.
  1. 현재 구현 상태: 실제 코드와 테스트 결과로 확인한다.
  2. 확정된 요구사항과 설계 의도: 최신 승인 문서로 확인한다. `openspec/specs/`(확정 스펙), archive된 change의 `design.md`, 명세서·기획서의 확정된 결정(`[결정]`). `[제안]`·`[확인 필요]`는 확정이 아니다.
  3. 코드와 설계가 어긋나면: 어느 쪽도 임의로 정답으로 삼거나 고치지 않는다. 불일치와 확인할 내용을 먼저 보고한다.
- 새 마이그레이션 번호는 `ls db/migrations | tail -1`로 정한다. 다른 브랜치가 같은 번호를 쓰고 있지 않은지도 본다.

### change를 끝낼 때 (순서대로)
1. `tasks.md` 모두 `[x]` → `npx --yes @fission-ai/openspec@1.14.3 archive <change> --yes`
2. `AGENTS.md` change 표에 다음 번호 줄을 더한다(마이그레이션 번호가 있으면 적는다)
3. `cd frontend && npm run trace` — `docs/추적표.md`는 손으로 고치지 않는다
4. `AGENTS.md` 7장 검사를 모두 돌린다. pytest는 DB가 필요하다: `docker compose up -d db`
5. PR 설명에 change 이름, 통과한 Scenario, 남은 `[확인 필요]`
6. 커밋한 뒤 `cd frontend && npm run sync-main -- --push` — 다른 세션 PR이 먼저 머지돼 표 번호·추적표가 겹쳐도 코드가 풀고 올린다. 머지가 "merge conflicts"로 막히면 다시 돌린다. 다른 파일이 겹치면 멈추고 알린다.

### E2E (Playwright, `frontend/e2e/`)
- CI에서는 돌지 않는다. PR 전에 로컬에서 돌린다.
- 준비: DB와 백엔드(8000, 제품표 `rfp-db seed-products` 적재), `cd frontend && npm run dev`(5173), 서버 `data/private/rfp_docx/`에 파일 1 원문(`review.spec`)과 합성 RFP 파일 28(`product-switch.spec`, `generate_risk_rfp.py` → `generate_switch_rfp.py`)(커밋 금지). 그다음 `cd frontend && npm run e2e`(한 파일만: `npx playwright test e2e/<이름>.spec.ts`). 다른 주소는 `E2E_BASE_URL`.
- 원문이 없으면 그 테스트는 건너뛴다(`test.skip`). "통과"로 보고하기 전에 건너뛴 수를 확인한다.

### 자주 걸리는 것
- docker compose는 `docker-compose.yml`의 `environment`에 적힌 변수만 백엔드에 넘긴다. `.env`에만 넣은 설정은 `uv run uvicorn`으로 직접 띄울 때만 읽힌다. 설정을 바꾼 뒤에는 `docker compose up -d backend`(`restart`는 환경변수를 다시 읽지 않는다).
- 새 설정 변수를 더하면 `config.py`, `.env.example`, `docker-compose.yml` 세 곳을 함께 고친다.
- 폴더 두 개에서 compose를 함께 띄우면 포트 5433·8000·5173·1025·8025가 겹친다.
- AI 문제는 `curl localhost:8000/api/health`로 `ai_mode`·`llm_configured`부터 본다. 키는 출력하지 말고 길이만 확인한다.
- 화면 문구가 스펙 시나리오에 적혀 있으면, 문구를 바꿀 때 change의 `specs/` delta도 함께 고친다.

### 글쓰기
- 사용자에게 보이는 문구는 쉬운 우리말로 쓴다. 번역투("글자로 찾음")와 가운뎃점 남발을 피한다.
- 내부 ID(R…, J…)보다 원문 위치를 먼저 보인다.
- 사용자 잘못이 아닌 상태(AI 없음, 대체 검색 등)는 중립색으로 보인다.

### 참고 문서
- 요구사항·기획: `docs/reference/기능요구사항명세서_v1.md`, `docs/reference/프로젝트기획서_v1.4.md`. `[제안]`·`[확인 필요]` 표시가 붙은 일정·기능은 확정이 아니다.
- 화면: `docs/screens/`(화면 명세 SCR-*, `_프런트원칙.md`). 추적: `docs/추적표.md`. 설치: `docs/setup-guide.md`, `README.md`.
- 각 change의 결정과 버린 대안: `openspec/changes/archive/<날짜-change>/design.md`.
- `docs/context/`는 저장소에 올리지 않는 개인 로컬 메모 자리다. 파일이 있으면 배경 참고로만 읽고, 없어도 작업에 필요하지 않다. 그 내용을 근거로 코드·스펙을 바꾸지 않는다.
