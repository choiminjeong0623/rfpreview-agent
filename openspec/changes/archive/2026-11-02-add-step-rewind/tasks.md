## 1. 흐름과 요청 (BE 나송주)
- [x] 1.1 `run.py` 담당자 확인의 `rewind` 동작·`rewind_to` 갈림, `execute_run(rewind=)`, `graph_flow.start_input`
- [x] 1.2 `doc_add.prepare_rewind` 검사·단계·이력, `POST /api/runs/{id}/rewind`, 스키마, `npm run gen:api`

## 2. 화면 (FE 나송주)
- [x] 2.1 이력 탭 단계 고르기·사유·[다시 처리], 이력 문장 `REWIND`, 흐름 기록 동작 이름

## 3. 시험과 마무리 (나송주)
- [x] 3.1 Scenario마다 테스트(`tests/test_step_rewind.py`, `e2e/step-rewind.spec.ts`)
- [x] 3.2 AGENTS.md 표, 추적표, archive
