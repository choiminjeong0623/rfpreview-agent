## Why

#177(update-pdf-drawings)을 VS Code 세션이 검토해 머지 전 고쳐야 할 세 가지를 재현했는데, 그 PR은 이미 main에 들어갔다. 이어서 고친다.

1. 도면 쪽 판별이 넓다: 본문 문장 "…showing the drawing no., revision and scale."만 있어도 도면 쪽이 되어 그 쪽 요구 문장이 모두 사라지고 그림 설명이 "도면 ,"으로 깨진다.
2. 기울임꼴(글자 행렬 c만 0이 아님, Word가 기울임꼴 없는 글꼴을 기울여 그림)도 "돌아간 글자"로 버려 문장이 사라진다.
3. 글자층이 깔린 그림 영역도 OCR해, 같은 내용이 잡음과 함께 한 번 더 들어간다(실제 구매 요청서에서 요구 40 → 48).

## What Changes

- 도면 쪽은 표제란 증거가 있을 때만: DRAWING NO·DWG NO와 SCALE이 표 칸이나 짧은 라벨 줄(30자 이하, "."로 끝나지 않고 shall·must 없음)에 있어야 하고, 그 쪽에 shall·must 줄이 2줄 이상이면 도면 쪽이 아니다. 번호를 못 찾으면 설명은 "도면"만.
- 실제로 돈 글자만 뺀다: 가로 성분 a가 0 이하이거나 각도 atan2(b, a)가 30°를 넘는 글자. 기울이기(b = 0, c만 있음)는 그대로 읽는다.
- 고른 그림 영역 안에 글자층 글자가 50자 이상이면 그 그림은 OCR하지 않는다(그림 위치는 남김).
- 마이그레이션 없음.

## Capabilities

### New Capabilities

### Modified Capabilities
- `document-intake`: PDF 쪽 속 그림 읽기, PDF 도면 쪽, PDF 돌아간 글자

## Impact

- `backend/src/rfp_agent/pipeline/pdf_reader.py`, `backend/tests/test_pdf_drawings.py`
