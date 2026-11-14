## 1. 흐름 기록 읽기 (BE 나송주)
- [x] 1.1 `graph_flow.history`: 저장된 상태를 오래된 순으로, 단계·끝난 시각·걸린 시간·바뀐 건수·사람 동작·멈춘 자리 (읽기만)
- [x] 1.2 `GET /api/runs/{run_id}/flow`, `schemas.py` 모델, `npm run gen:api`

## 2. 화면 (FE 나송주)
- [x] 2.1 실행 기록 펼친 줄에 흐름 기록(펼칠 때 부름), 이름표(`labels.ts`), `SCR-25_공유.md`

## 3. 시험과 마무리 (나송주)
- [x] 3.1 Scenario마다 테스트(`tests/test_flow_history.py`, `e2e/flow-history.spec.ts`)
- [x] 3.2 AGENTS.md 표, 추적표, archive
