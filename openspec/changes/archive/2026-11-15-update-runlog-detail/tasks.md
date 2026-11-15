## 1. 화면

- [x] 1.1 `RunLog.tsx`: 줄 누르기·Enter → `#/runlog/:id`, 펼치기 없앰. `RunLogDetail` 상세 화면
- [x] 1.2 `App.tsx`: `/runlog/:id` 경로, 현재 위치 "홈 > 시스템 관리 > 실행 기록 > 상세"
- [x] 1.3 e2e `run-log.spec.ts`·`flow-history.spec.ts`: 상세 화면으로 이동해 확인
- [x] 1.4 문서: `SCR-25_공유.md`

## 2. AI 호출 응답

- [x] 2.1 `pipeline/ai_calls.summary`: 응답에서 `run_token` 뺌, pytest에서 `AiCalls` 모양 검사

## 3. 마무리

- [x] 3.1 검사(ruff·pytest·lint·check:api·check:trace·build·openspec validate)
- [x] 3.2 archive, AGENTS.md 표, `npm run trace`
