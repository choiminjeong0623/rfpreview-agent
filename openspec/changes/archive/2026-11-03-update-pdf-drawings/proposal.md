## Why

도면이 든 합성 PDF(글자 쪽·CAD 단선도 쪽·글자 쪽에 박은 도면 그림·스캔 쪽·돌아간 글자 쪽)를 AI 없이 돌려 보니 PDF 읽기가 도면을 다루지 못했다.

- 글자가 있는 쪽에 박은 그림은 OCR도 하지 않고 그림 위치도 남기지 않아, 문서 읽기 점검이 "그림 0"으로 놓친 곳을 보이지 않았다. docx는 그림을 OCR하고 위치를 남긴다.
- CAD 단선도 쪽은 같은 높이의 라벨이 쪽 너비로 한 줄이 되어 "CB 52-1 CB 52-2 CB 52-3 3150A 3150A 3150A …"처럼 섞이고, 기호 상자가 빈 표로, 표제란이 "표 칸을 읽지 못함" 점검으로 잡혔다.
- 90°·45°로 돌아간 글자는 "ELBAC", "Vk33"처럼 한 글자씩 깨진 단락이 되었다.

## What Changes

- 글자 쪽의 큰 그림(쪽 넓이 5 % 이상)은 그림 위치로 저장하고, OCR 엔진이 있으면 그 영역을 OCR로 읽어 그림 뒤 단락으로 더한다(docx와 같게).
- 표제란 낱말(DRAWING NO·DWG NO와 SCALE)이 있는 쪽은 도면 쪽: 라벨·치수·표제란은 단락·표로 읽지 않고 "NOTE"로 시작하는 주기 줄만 줄마다 단락으로 읽는다. 쪽에 그림 하나("도면 <번호> · <제목>")를 남겨 문서 읽기 점검에 보인다.
- 가로가 아닌 글자는 줄로 읽지 않고 그 쪽에 그림 하나("돌아간 글자 n자")를 남긴다.
- 도면 기호·연결 해석은 그대로 범위 밖. 마이그레이션 없음(그림 위치 표 그대로). 처리 코드가 바뀌어 PDF는 다시 처리된다(code_version).

## Capabilities

### New Capabilities

### Modified Capabilities
- `document-intake`: PDF 쪽 속 그림 읽기, PDF 도면 쪽, PDF 돌아간 글자 (ADDED)

## Impact

- `backend/src/rfp_agent/pipeline/pdf_reader.py`, `docx_reader.py`(Block 그림 설명 칸, find_figures)
- `backend/tests/test_pdf_drawings.py`
- 범위 밖으로 남김: PDF 원문 위치의 쪽 번호(위치 모양·화면이 바뀜, 따로)
