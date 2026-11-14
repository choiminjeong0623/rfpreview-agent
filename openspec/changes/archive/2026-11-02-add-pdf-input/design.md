# 설계: add-pdf-input

## 결정

### 1. 읽기 모듈 (`pipeline/pdf_reader.py`, `pipeline/reader.py`)
- 라이브러리 **pdfplumber**(MIT). 표 찾기(`page.find_tables`)와 글자 줄 위치(`extract_text_lines`)를 준다. PyMuPDF는 AGPL이라 버림.
- `reader.read_document(path)`: 확장자로 `docx_reader.read_blocks` 또는 `pdf_reader.read_blocks`를 고른다(코드). `document.py`·`preview`는 이 함수만 부른다.
- PDF 블록 만들기(쪽 순서대로):
  - 표: `find_tables()`의 행마다 `Block(kind="R", cells=…, raw_cells=…, table_no=문서 안 표 번호)`. 빈 칸은 ""(병합 칸은 pdfplumber가 None → "").
  - 표 밖 글자: 표 영역(bbox) 밖 줄만. 줄 위아래 간격이 줄 높이의 1.5배를 넘거나, 줄이 번호 패턴("1.", "1.1", "A.", "PART 1")으로 시작하면 새 단락. 단락 안 줄은 줄바꿈으로 이어 `text`, `line_count` = 줄 수.
  - 줄 번호는 문서 처음부터 블록마다 이어 센다(docx와 같은 방식, `line_no`·`last_line`).
  - 쪽 머리말·꼬리말: 같은 글자가 쪽 절반 이상에서 같은 높이(위 5 %·아래 5 %)에 반복되면 뺀다(쪽 번호 등).
- 글자 층이 없으면(모든 쪽 글자 0) 블록 0개 → 분류에서 판독 불가(지금 기준 `MIN_READABLE_LINES`). 열 수 없는 PDF(암호·깨짐)도 블록 0개.
- `txt` 줄 맞추기(`line_map`)는 docx만. `find_figures`는 PDF에서 빈 목록.
- **[구현 때 바뀜]** 문서의 줄 번호 기준 칸(`line_basis`) 제약이 TXT·DOCX만 받아 PDF를 더하는 마이그레이션 **0036**이 필요했다. 머리말·꼬리말 빼기는 2쪽 이상에서 반복될 때만이라 1쪽짜리 PDF의 쪽 번호 줄은 단락으로 남는다(요구사항은 아님).
- 처리 판: `DOCUMENT_MODULES`에 `pdf_reader`, `reader`를 더해 코드 판에 들어가게 한다.

### 2. 받는 곳
- API `_safe_name`: `.docx`·`.pdf`만(안내 "docx·PDF 파일만 받습니다"). 서버 목록은 `*.docx`·`*.pdf`. 분류 추천·문서 추가도 같은 검사.
- 화면 `accept=".docx,.pdf"`, 안내 글자 "docx·PDF". e2e가 쓰는 `aria-label`은 그대로 둔다.

### 3. 시험 자료
- 테스트에서 **reportlab**(BSD, dev 의존성)으로 PDF를 만든다: 데이터시트 표(쪽 넘김 포함) + shall 문장. 같은 내용을 `docx_factory`로 docx로도 만들어 요구사항 수를 비교한다.
- 스캔 PDF: 글자 없이 사각형만 그린 PDF.

## 대안
- PDF → docx 변환 뒤 기존 경로: 변환기(LibreOffice) 설치·품질 문제. 버림.
- AI로 PDF 읽기: 원문을 외부로 보내고 숫자를 AI가 만들게 됨(CR-01·04). 버림.

## 위험
- PDF 표 찾기는 선이 없는 표에서 약하다. 못 찾은 표는 글자 줄로 들어와 문장 규칙으로만 뽑힌다(문서 읽기 점검에 남음).
- 두 단 편집 PDF는 읽는 순서가 섞일 수 있다 [확인 필요].
