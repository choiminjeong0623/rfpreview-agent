## 1. 역할별 AI 호출 지표 (P1-1)

- [x] 1.1 `pipeline/ai_calls.py` `role_stats(rows)`: 요청 묶기·p50·p95·실패율·버린 비율·재시도 뒤 성공, `summary`에 `roles`
- [x] 1.2 `api/schemas.py` `AiCallRoleStat`, `AiCalls.roles`, `npm run gen:api`
- [x] 1.3 실행 기록 상세 AI 호출에 역할별 표
- [x] 1.4 테스트: Scenario "역할별 지표"(가짜 기록), "호출 기록 없음"(빈 목록)

## 2. 평가 중 비용 상한 (P1-5)

- [x] 2.1 `prompt_eval.evaluate`: 묻기 전 쓴 비용 확인, 넘으면 `BUDGET` 답, 남은 반복 멈춤, `FAILED` + 이유
- [x] 2.2 테스트: Scenario "평가 중 상한을 넘음"(가짜 모델이 토큰을 많이 씀, 순차 1 worker), 확인 옵션이면 어림 두 배까지

## 3. 사람 수정 비율 (P1-8)

- [x] 3.1 `review.bulk_confirm` 이력 이유 "한꺼번에 확정"
- [x] 3.2 `evaluation.metrics`에 `EDIT-RATE`(예전 이력은 같은 시각으로 구분)
- [x] 3.3 테스트: Scenario "사람 수정 비율"

## 4. 마무리

- [x] 4.1 docs/05-evaluation.md·운영 문서에 지표 설명
- [x] 4.2 검사 모두, archive, AGENTS 줄, 추적표
