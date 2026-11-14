# 설계: add-kind-extract-rules

## 결정

### 1. 처리기 표에 추출 규칙 (`pipeline/processors.py`)
`Processor.rules: frozenset[str]`(기본 빈 집합).
```
SUPPLIER_SPEC  {MARK_TABLE_ROWS}
BID_FORM       {FORM_NOTES}
나머지·일반     {}
```
- `_prepare`가 `extract(blocks, sections, tables, proc.rules, risk_patterns)`로 넘긴다. 규칙 이름과 표현은 `pipeline/extract.py`에 둔다(추출 규칙은 추출 모듈 한 곳).
- 점검 뒤 다시 묻기(update-partial-reprocess)는 AI 단계만 다시 하므로 추출 결과는 처음 처리기 규칙 그대로다.

### 2. MARK_TABLE_ROWS (공급사 답안 표 조항 줄)
- 문서의 표 중 한 줄이라도 C/D/E 표시가 있으면(`build_tables(supplier_marks=True)`가 읽은 표시), 모든 표의 행 중 데이터시트가 아니고 조항 줄인 행을 `SUPPLIER_ANSWER` 후보로 뽑는다. 조항 줄 = 가장 긴 칸이 15자 이상이고 소문자가 있음(요구사항 정답지의 조항 기준과 같은 값, `req_eval.MIN_CLAUSE`).
- 규칙 번호 `E-MARK-TABLE-ROW`, 표시는 없으면 NULL(CR-04). 표시를 읽은 줄은 지금처럼 `E-SUPPLIER-MARK`.
- 처음 시도는 "표시가 있는 표만"이었다(K1 81.0 %). 같은 문서의 다른 표(설치·시험 조항)도 답안 조항이라 문서 전체로 넓혔다(K1 100 %, K2 95.6 %).

### 3. FORM_NOTES (입찰 서식 작성 안내)
- 표 밖 문장 후보 중 `FORM_NOTE` 표현이 든 요구사항 문장을 `WRITING_RULE`, 규칙 번호 `E-FORM-NOTE`로 바꾼다. 위험 표현 사전(`risk_expressions`) 패턴이 든 문장은 바꾸지 않는다(`_refine_with_ai`가 위험 표현 문장을 AI에 묻지 않는 것과 같은 이유).
- 표 칸(TABLE_CELL)은 건드리지 않는다.
- Bidding Forms에서 표 밖 요구 문장 62줄 중 18줄이 바뀐다(19줄 중 위험 표현 1줄은 그대로).

### 4. 처리 판
- 추출 코드가 바뀌어 `code_version`이 바뀌므로 같은 파일도 새로 처리한다. 프롬프트는 그대로(p6).

## 측정 (로컬, 규칙만, 2026-11-02)
| 문서 | 지표 | 전 | 후 |
|---|---|---|---|
| RFP18 Electric Distribution (공급사 답안, 정답 200줄) | K1 | 133/200 = 66.5 % | 200/200 = 100 % |
| 같은 문서 | K2 | 143/153 = 93.5 % | 216/226 = 95.6 % |
| Bidding Forms | 표 밖 요구 문장 | 62 | 44 (작성 규칙 18) |
- 한계: 공급사 답안 정답지도 "답안 표의 조항 줄"이라 규칙과 정의가 같다. 정답지 코드는 구조 단계 코드를 쓰지 않고 docx를 직접 읽어 같은 코드에서 나오지는 않는다.

## 대안
- 공급사 답안의 모든 문장을 후보로: 표지·목차 줄까지 들어와 K2가 떨어진다.
- 입찰 서식 표 밖 문장 전부를 작성 규칙으로: 가격 고정·보증 같은 상업 조건 문장(FR-16)이 빠진다. 버림.

## 위험
- 공급사 답안 후보가 늘어 판정 대상(묶음 A·B)이면 판정 줄도 늘 수 있다. RFP18은 묶음 C라 판정하지 않는다.
- 보증 기술 특성표(파일 1)는 그대로 0줄 [확인 필요].
