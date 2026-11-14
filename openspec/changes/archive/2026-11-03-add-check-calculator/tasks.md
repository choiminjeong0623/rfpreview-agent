## 1. 서버

- [x] 1.1 `pipeline/engineering.py`: `peak_check` 순수 함수(분석과 같은 FACTORS·matches·r10)
- [x] 1.2 `GET /api/engineering/peak-check`, 응답 모양 `PeakCheck`(schemas), `npm run gen:api`
- [x] 1.3 pytest: Scenario "검산 계산 확인", "배수 없는 주파수"

## 2. 화면

- [x] 2.1 `views/JudgeView.tsx`: "검산 확인" 상자(원문 값 채움, 고치면 계산, [원문 값으로], 참고 안내)
- [x] 2.2 e2e: Scenario "판정 상세에서 검산 확인"

## 3. 마무리

- [x] 3.1 검사(AGENTS.md 7장)
- [x] 3.2 archive, AGENTS.md 표, `npm run sync-main`
