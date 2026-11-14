## 1. 문서

- [x] 1.1 명세서 CR-07에 "AI 답 검사 보강 [제안 11-01]", 기획서 4장 표(FR-06·FR-09)에 검사 보강을 적는다

## 2. AI 답 형식 (llm/tasks.py)

- [x] 2.1 `labels`·`types`·`texts` 답을 줄 번호 객체로 받고 번호를 검사해 줄 세운다
- [x] 2.2 `draft_sentences`가 줄마다 자리표시자를 모두 썼는지 보고, 아니면 None
- [x] 2.3 `explain_risk`: 문장마다 그 문장 근거 조각·사실의 숫자만 허용, 배수 말 검사, 버린 이유 돌려줌

## 3. 저장과 응답

- [x] 3.1 마이그레이션 0024 `risk_flag.explanation_drop_reason`
- [x] 3.2 `_save_risks`가 버린 이유 저장, 위험 조건·실행 기록 응답에 이유·건수
- [x] 3.3 outputs·proposals가 None 줄을 코드 기본 문장(CODE)으로
- [x] 3.4 `npm run gen:api`

## 4. 화면

- [x] 4.1 실행 기록 화면 "AI 설명 버림 n", 위험 조건 탭 버린 이유

## 5. 테스트

- [x] 5.1 테스트 대역(FakeLLM 등)을 번호 답으로 바꾼다
- [x] 5.2 Scenario마다 테스트
- [x] 5.3 백엔드·프런트 검사, `openspec validate --all --strict`
