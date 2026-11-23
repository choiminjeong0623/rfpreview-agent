# Tasks

## 1. 실패하는 테스트 먼저

- [x] 1.1 `tests/test_run_queue.py`에 Scenario "단계 저장 직전에 밀려남": 옛 작업(토큰 A)을 꺼내 돌리며 `judge_run`을 감싸 판정을 쓴 뒤 다른 연결로 `enqueue`(토큰 B). 옛 실행은 `"SUPERSEDED"`, 그 검토 판정 0건, 단계는 처리 중 그대로(새 실행 하나만 쓰는 것은 기존 Scenario "취소 직후 다시 시도"가 봄). 확인: 지금 코드에서 판정 18건 남아 **실패**
- [x] 1.2 문서 병렬 처리(`RFP_DOC_WORKERS=2`, 문서 2개) 연결에서 `_save_run_document` 앞에 다시 넣는 테스트. 확인: 지금 코드에서 run_document 1건 남아 실패

## 2. 저장 순간 확인

- [x] 2.1 새 `pipeline/ownership.py`(`RunSuperseded`를 run.py에서 옮김): `ensure_owned(conn, run_id, token)`(`SELECT … FOR UPDATE`, 다르면 `RunSuperseded`), 감싸개 `OwnedConnection`(속성은 원래 연결로, `commit()`만 확인 뒤 커밋)
- [x] 2.2 `execute_run`이 `ctx.token`이 있으면 `ctx.conn`을 감싸고, `graph_flow.open_like`가 감싼 연결이면 감싼 연결을 돌려줌. 토큰 없는 실행은 그대로
- [x] 2.3 바깥 `with conn.transaction():` 블록(처리 흐름이 부르는 모듈 10곳 넘음)은 감싸개의 `transaction()`이 블록 끝에서 `ensure_owned`. 확인: 단위 시험 "바깥 transaction() 블록도 끝에서 확인해 되돌린다"
- [x] 2.4 `run_queue.enqueue`·`reclaim`에 잠금 순서 주석 한 줄(같은 행 UPDATE로 순서가 정해짐). 코드 동작은 그대로
- [x] 2.5 확인: 1.1·1.2 통과, 기존 `test_run_queue.py`·`test_run_control.py`·`test_graph_stops.py` 통과

## 3. 문서

- [x] 3.1 `docs/08-known-limits.md` "대기열 소유권 확인은 '확인한 뒤 쓰기'" 줄을 해결됨으로(남는 한계: 살아 있음 판단은 그대로)
- [x] 3.2 `docs/03-adr.md` ADR-013: 커밋 직전 행 잠금으로 펜싱, 버린 대안

## 4. 통합 확인

- [x] 4.1 AGENTS.md 7장 검사 모두 통과: ruff, pytest(DB), `npm run lint`·`check:api`·`check:trace`·`build`, `openspec validate --all --strict`

## Workflow follow-up

- `npx --yes @fission-ai/openspec@1.14.3 archive update-run-fencing --yes`
- AGENTS.md change 표에 다음 번호 줄(마이그레이션 없음)
- `cd frontend && npm run trace`
- PR 설명에 change 이름, 통과한 Scenario, 고치기 전 실패 출력, 남은 `[확인 필요]`
- 커밋 뒤 `cd frontend && npm run sync-main -- --push`
