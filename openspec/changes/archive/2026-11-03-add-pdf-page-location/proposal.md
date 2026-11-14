## Why

PDF 원문 위치가 docx처럼 "파일 · 절 · n행"만 보여서, 엔지니어가 PDF를 열어 그 줄을 찾으려면 몇 쪽인지 알 수 없었다. 도면 쪽(update-pdf-drawings)처럼 절 제목이 없는 쪽은 앞 쪽의 절 번호를 이어받아 "1절"로 보여 더 헷갈렸다. PDF 사람이 보는 기준은 쪽이다.

## What Changes

- PDF를 읽을 때 쪽마다 첫 줄 번호를 문서에 저장한다(docx는 저장하지 않음).
- 원문 위치 응답에 쪽 번호 `page`를 더한다(PDF만, docx는 비움). 줄 번호로 코드가 정한다(CR-01).
- 화면·내보내기(일탈·질의 Word, TBE 엑셀)·문서 읽기 점검의 원문 위치를 "파일 · n쪽 · 절 또는 표 · n행"으로 보인다.
- 마이그레이션 0039(문서 쪽 시작 줄, 줄 → 쪽 함수). 처리 코드가 바뀌어 PDF는 다시 처리되어 쪽이 채워진다.

## Capabilities

### New Capabilities

### Modified Capabilities
- `document-intake`: PDF 원문 위치의 쪽 번호 (ADDED)

## Impact

- `db/migrations/0039_pdf_page.sql`, `pipeline/pdf_reader.py`·`docx_reader.py`(Block.page)·`document.py`·`queries.py`·`read_checks.py`·`export.py`·`tbe.py`, `api/schemas.py` Location
- 화면 `components/labels.ts` locationText, `docs/screens/_공통규칙.md` 3장, `npm run gen:api`
