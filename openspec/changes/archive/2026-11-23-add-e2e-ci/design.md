# Design: add-e2e-ci

## Decisions

### D1. 준비는 저장소에 있는 것만
- DB: GitHub Actions `postgres:16` 서비스, DB 이름 `rfp_e2e`. `rfp-db setup`(마이그레이션·규칙 사전·실제 제품표).
- 합성 데이터시트(`e2e/fixtures/synthetic_judgment.docx`)는 문서 목록에 없어서 판정이 생기지 않는다. 기준 데이터(`document_catalog.csv`)에 넣지 않고 CI에서만 문서 목록 줄(91, 묶음 A)을 넣는다. 기준 데이터에 시험 파일을 섞지 않기 위해서다.
- 로그인: `rfp-db set-password --login engineer|approver --password-stdin`, 값은 `E2E_PASSWORD` 기본값과 같은 시험용 문자열(비밀값 아님).
- 백엔드: `RFP_AI_MODE=off`, `RFP_RUN_MODE=inline`. 프런트: `npm run dev`(Vite 프록시가 /api를 8000으로).

### D2. 건너뛰기를 실패로
`core-flow.spec.ts`는 준비가 빠지면 `test.skip`한다. 로컬에서는 편하지만 CI에서 skip은 "검사 안 함"이다. Playwright JSON 결과(`PLAYWRIGHT_JSON_OUTPUT_NAME`)를 `scripts/check-e2e-report.mjs`가 읽어 `stats.skipped > 0`이거나 `expected == 0`이면 실패한다. 실패·예상 밖 결과도 실패.
- 버린 대안: 테스트 안의 `test.skip`을 지우기. 로컬 개발자가 원문 없이 돌릴 때 이유가 보이는 편이 낫다.

### D3. 돌리는 파일
`core-flow.spec.ts`(실제 백엔드로 끝까지)와 `evaluation.spec.ts`(채점 화면, 일부 응답은 page.route). 둘 다 메일·원문 없이 돈다. 전체 e2e는 Non-Goal.

### D4. 시간
chromium 설치(`npx playwright install --with-deps chromium`) 약 1분, 시험 약 30초. backend 작업과 병렬이라 PR 대기 시간에는 거의 더하지 않는다.
