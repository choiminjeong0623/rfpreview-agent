# Tasks

## 1. 회귀 판정

- [x] 1.1 `pipeline/prompt_eval.py`: 지표 재료에 `short`·`questions`, 반복 합칠 때 `min_short`, 기준선 요약에 문항 재료, `compare`는 모자란 문항이 허용 문항 수보다 늘면 회귀(예전 기준선은 분모로 어림), 회귀 줄 "n문항 떨어짐(허용 m문항)"
- [x] 1.1a `api/schemas.py` 지표 칸, `npm run gen:api`
- [x] 1.2 테스트: Scenario "문항이 적은 지표의 한 문항 흔들림"·"한 문항에서 근거 문장 여럿이 빠짐", 기존 회귀·반복 테스트 통과

## 2. 재측정과 문서

- [x] 2.1 기준선 다시 만들기(문항 재료, 3번 반복)와 그 기준선으로 재측정(Gemini 3.8 Flash), 결과를 `docs/05-evaluation.md`에
- [x] 2.2 `docs/07-troubleshooting.md` 7-3 고침(CI가 아니라 로컬 실행이었음, 재측정에서 다시 나온 회귀와 이번 해결), `docs/03-adr.md` ADR-009 결과
- [x] 2.3 `data/eval/README.md` 회귀 규칙 설명
