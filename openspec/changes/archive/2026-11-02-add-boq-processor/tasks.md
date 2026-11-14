## 1. 문서 종류 코드 BOQ (BE 나송주)
- [x] 1.1 마이그레이션 0033: 문서·문서 종류 규칙의 문서 종류 제약에 `BOQ`
- [x] 1.2 `schemas.DocKind`, `seed.DOC_KINDS`, `tasks.DOC_KINDS`·문서 종류 질문 문장, `PROMPT_VERSION` p6, `npm run gen:api`
- [x] 1.3 화면 `DOC_KIND_NAMES` 물량표, `docs/screens/_공통규칙.md`

## 2. 규칙과 처리기 (BE 나송주)
- [x] 2.1 `data/seed/doc_kind_rules.csv` 물량표 줄(순서 6)
- [x] 2.2 `Stats.table_rows`, 처리기 표 물량표(설명·표 줄 0 점검, 다시 묻지 않음)

## 3. 시험과 마무리 (BE 나송주)
- [x] 3.1 Scenario마다 테스트, 문서 종류 규칙 줄 수 5 → 6
- [x] 3.2 AGENTS.md 표, 추적표, archive
