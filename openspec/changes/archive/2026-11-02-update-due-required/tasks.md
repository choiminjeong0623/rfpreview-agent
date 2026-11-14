## 1. 백엔드

- [x] 1.1 `review_info.require_due`: 시작할 때 마감일이 없으면 400, 고치기에서 마감일을 비우면 400
- [x] 1.2 `rfp-review run --due-in`(기본 14), `rfp-db fill-due --due-in`(빈 마감만, 시작일 + N일, 이력)
- [x] 1.3 pytest: Scenario "마감일 없이 시작", "마감일 비우기", "빈 마감 채우기", 검토를 만드는 테스트에 마감일

## 2. 화면 테스트

- [x] 2.1 e2e: 검토를 만드는 도우미·테스트에 마감일, "검토명이 빈 검토"는 마감 D-day가 보임

## 3. 마무리

- [x] 3.1 검사(ruff·pytest·lint·check:api·build·openspec validate)
- [x] 3.2 archive, AGENTS.md 표, `npm run trace`
