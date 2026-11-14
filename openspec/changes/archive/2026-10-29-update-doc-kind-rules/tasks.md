# Tasks

## 1. 사전

- [x] 1.1 마이그레이션 `0012_doc_kind_rules.sql`
- [x] 1.2 `data/seed/doc_kind_rules.csv` (지금 5줄 그대로)
- [x] 1.3 `seed_doc_kind_rules` (정규식·종류 코드 검사)

## 2. 분류

- [x] 2.1 `classify`가 적재된 규칙을 쓰게 바꾸고 코드 목록 지우기 (`dictionaries`, `preview`)

## 3. API·화면

- [x] 3.1 `GET /api/rules/doc-kinds`, `DocKindRule`, `npm run gen:api`
- [x] 3.2 판정 규칙 화면 "문서 종류" 탭, SCR-17 명세·공유 갱신

## 4. 테스트 (Scenario마다 하나 이상, 이름에 Scenario 이름)

- [x] 4.1 백엔드: 사전 순서대로 문서 종류 정하기 / 사전에 없는 표현 / 문서 종류 규칙 두 번 적재 / 모르는 문서 종류 / 문서 종류 규칙 보기
- [x] 4.2 화면: 문서 종류 규칙 탭 (`e2e/reference.spec.ts`)

## 5. 마무리

- [x] 5.1 ruff, pytest, lint, check:api, build, `openspec validate --all --strict`
- [x] 5.2 archive
