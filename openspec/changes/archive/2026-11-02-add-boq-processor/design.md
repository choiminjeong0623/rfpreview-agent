# 설계: add-boq-processor

## 결정

### 1. 코드 `BOQ` (이름 "물량표")
문서 종류 목록이 흩어져 있어 한 번에 바꾼다.
- DB: 마이그레이션 0033 — `document_doc_kind_check`, `doc_kind_rule_doc_kind_check`를 지우고 `BOQ`를 더해 다시 건다(있는 마이그레이션은 고치지 않음).
- `api/schemas.py` `DocKind`, `db/seed.py` `DOC_KINDS`, `llm/tasks.py` `DOC_KINDS`와 문서 종류 질문 문장(`BOQ=물량표`), `PROMPT_VERSION` p6.
- 화면 `components/labels.ts` `DOC_KIND_NAMES`에 `BOQ: '물량표'`. 등록 화면·문서 표·규칙 고치기 창의 선택지는 이 표에서 나와 저절로 늘어난다. `docs/screens/_공통규칙.md` 문서 종류 줄. `npm run gen:api`.

### 2. 문서 종류 규칙 한 줄 (`data/seed/doc_kind_rules.csv`)
```
6,BOQ,boq|bill of quantit|물량,\bbill of quantities\b,물량표 (품목·수량·단위 표)
```
- 순서 6(맨 뒤): 앞 줄과 겹치지 않는 표현이라 맨 뒤여도 된다. 우선순위 번호를 다시 매기면 사람 고침 이력과 어긋날 수 있어 피한다.
- 파일 이름 `"Bidding Forms … BOQ"`는 입찰 서식 줄(순서 1)이 먼저 이긴다(지금 사전 순서 규칙 그대로).

### 3. 처리기 (`pipeline/processors.py`)
```
BOQ  물량표  hint: 물량표(BOQ). 품목·수량·단위 표가 대부분이고 기술 요구 문장은 적다.
             check: 표 줄 0  fix: 없음
```
- `Stats`에 `table_rows`(논리 표의 행 수)를 더한다. 표 칸 요구값(`table_cells`)은 요구값·보증값 칸이 있는 표만 세므로, 수량 칸만 있는 물량표는 늘 0이 되어 점검에 쓸 수 없다.
- 표 줄은 AI에 묻지 않아 다시 물어도 같으므로 `fix` 없음.

## 대안
- 물량표를 입찰 서식으로 두기: 입찰 서식 점검(표 칸 요구값 0)에 늘 걸려 확인 필요가 쏟아진다. 버림.
- 단선도 처리기: 도면이라 docx 글자가 거의 없다(판독 불가로 분류). OCR 범위 밖이라 버림.

## 위험
- 프롬프트 판이 바뀌어 처음 한 번은 같은 파일도 새로 분석한다(AI 비용).
- 실제 물량표 파일이 이름·첫 장 표현에 안 맞으면 여전히 종류 모름. 사람이 등록 화면에서 고르거나 규칙 화면에서 표현을 더한다.
