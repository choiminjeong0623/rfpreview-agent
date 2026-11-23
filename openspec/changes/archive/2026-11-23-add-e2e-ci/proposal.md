# Proposal: 핵심 흐름 e2e를 CI에서 (add-e2e-ci)

## Why

핵심 흐름 e2e("RFP 한 건 처음부터 끝까지": 올리기 → 분석 → 판정 확정 → 상신 → 승인 → 인계 패키지)는 있지만 CI에서 돌지 않는다(CLAUDE.md "CI에서는 돌지 않는다. PR 전에 로컬에서 돌린다"). 2026-11-22 포트폴리오 점검 P0-5: 화면 흐름이 깨져도 PR이 초록으로 머지될 수 있고, 로컬에서도 준비가 빠지면 `test.skip`으로 건너뛰어 "통과"처럼 보인다.

## What Changes

1. CI에 `e2e` 작업을 더한다: PostgreSQL 서비스, 마이그레이션·규칙 사전·실제 제품표, 합성 데이터시트 문서 목록 줄(묶음 A), 엔지니어·승인자 비밀번호, AI 끔·inline 실행으로 백엔드(8000), `npm run dev`(5173), Playwright chromium.
2. `e2e/core-flow.spec.ts`와 `e2e/evaluation.spec.ts`를 돌리고, 하나라도 실패하거나 **건너뛰면** 작업이 실패한다(`scripts/check-e2e-report.mjs`가 Playwright JSON 결과를 읽어 건너뛴 수 0, 돈 수 1 이상을 확인).
3. 실패하면 스크린샷·결과를 내려받을 수 있게 올린다.
4. 문서: CLAUDE.md E2E 절, `docs/setup.md` 준비 단계(문서 목록 줄을 한 명령으로).

## Non-Goals

- e2e 전체를 CI에서 돌리기. 메일(SMTP)·고객 원문·견적 데이터가 필요한 시험이 있다. 이 change는 준비 없이 도는 두 파일만.
- 화면·API·스펙 동작 바꾸기. 마이그레이션 없음.

## Capabilities

### Modified Capabilities

- `spec-verification`: "핵심 흐름 e2e"에 CI에서 PR마다 돌고 건너뛰면 실패한다는 것을 더한다.
