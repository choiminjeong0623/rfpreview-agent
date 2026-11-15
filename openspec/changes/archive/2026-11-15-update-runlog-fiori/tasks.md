## 1. 단계 시간

- [x] 1.1 `pipeline/run.py` `_set_step`·`_close_step`: `clock_timestamp()`
- [x] 1.2 pytest "단계 시간이 다음 단계로 밀리지 않음" (고치기 전 실패 확인)

## 2. 화면

- [x] 2.1 `RunLog.tsx` `RunLogDetail`: 머리글 KPI 가장 오래 걸린 단계, 구역 이동, 카드
- [x] 2.2 단계별 처리 한 표(걸린 시간 막대·AI 시간·바뀐 것·사람 동작·멈춘 자리, 회차 고르기)
- [x] 2.3 AI 호출 거르기(단계·역할 고르기, 느린 순, 초기화, m / n건, 결과 없음), "분석 밖"
- [x] 2.4 프롬프트 판 접기, ⓘ 설명. `detail.css`
- [x] 2.5 e2e `run-log.spec.ts`·`flow-history.spec.ts`, 문서 `SCR-25_공유.md`

## 3. 마무리

- [x] 3.1 검사(ruff·pytest·lint·check:api·check:trace·build·openspec validate)
- [x] 3.2 archive, AGENTS.md 표, `npm run trace`
