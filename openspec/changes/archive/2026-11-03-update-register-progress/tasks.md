## 1. 화면

- [x] 1.1 `api.ts`: `upload(files, info, choices, onProgress?)` — onProgress가 있으면 XMLHttpRequest로 보내 업로드 바이트를 알림
- [x] 1.2 `views/Register.tsx`: 등록하는 동안 진행 막대·설명(파일 올리는 중 크기·퍼센트 → 검토 만드는 중), 실패하면 지움
- [x] 1.3 e2e: Scenario "검토 등록 진행 표시"

## 2. 마무리

- [x] 2.1 검사(lint·check:api·check:trace·build·openspec validate)
- [x] 2.2 archive, AGENTS.md 표, `npm run sync-main`
