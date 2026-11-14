## 1. 저장소와 흐름 모양
- [x] 1.1 `uv add langgraph-checkpoint-postgres`, `uv.lock` 커밋
- [x] 1.2 `rfp-db setup`·`migrate`와 테스트 DB 준비에서 `PostgresSaver.setup()` 부르기
- [x] 1.3 `build_graph`에 checkpoint 저장소를 받고 `thread_id = run-<run_id>`로 돌리기
- [x] 1.4 사람 노드 `engineer_review`·`approval`·`rejected`와 동작 이름 → 다음 노드 갈림 표

## 2. 사람 동작을 흐름에서 잇기
- [x] 2.1 `pipeline/graph_flow.py`: `advance(conn, run_id, action)`, 멈춘 자리와 동작 대조(다르면 409), 흐름 기록 없으면 그대로 [구현 때 바뀜: design 2장]
- [x] 2.2 `finish_review`·`decide`·`withdraw`·`reopen`이 트랜잭션 끝에서 `advance`를 부름 (API 끝점은 그대로)
- [x] 2.3 문서 추가: 검사·기록 뒤 `execute_run`이 담당자 확인 자리면 `add_documents`로 이어 감

## 3. 이어서 다시 시도
- [x] 3.1 `execute_run`이 흐름이 처리 중간에 멈춰 있으면 `invoke(None)`로 이어 감, 없으면 처음부터
- [x] 3.2 `graph_state.resumed_from`·`skipped_steps`, `RunLogItem.resumed_from`, `npm run gen:api`

## 4. 시험과 마무리
- [x] 4.1 Scenario마다 테스트(`tests/test_graph_stops.py`)
- [x] 4.2 지금 테스트(결재·취소·다시 시도·문서 추가) 그대로 통과
- [x] 4.3 AGENTS.md 표, 개발 기록, archive
