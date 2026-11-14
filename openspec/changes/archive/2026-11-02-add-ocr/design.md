# 설계: add-ocr

## 결정

### 1. 엔진과 호출 (`pipeline/ocr.py`)
- **Tesseract**(Apache-2.0)를 `pytesseract`(Apache-2.0)로 부른다. 언어 `eng+kor`, `--psm 6`(한 덩어리 글). 결과는 `image_to_data`로 단어·줄·신뢰도를 받는다.
- 줄 신뢰도 = 줄 단어 신뢰도 평균. **60 미만 줄은 버린다**(지어내지 않음, CR-04) [제안].
- 같은 엔진 판 + 같은 그림이면 같은 결과다. `ocr.engine_version()`을 처리 판(`RunContext.processing_key`)에 붙여 엔진이 바뀌면 새로 분석한다(CR-11). 엔진이 없거나 `RFP_OCR=off`면 판에 `ocr-off`.
- 설정 `RFP_OCR`(기본 on). 엔진이 없으면 꺼진 것과 같다(오류 아님).

### 2. 어디서 읽나
- **PDF**(`pdf_reader`): 쪽에 글자 줄이 하나도 없고 엔진이 있으면 쪽을 300 dpi 그림으로 만들어(`page.to_image`, pypdfium2) OCR. 줄을 지금 단락 묶기(`_paragraphs`)에 넣는다(위치 키 `top`·`bottom`은 그림 좌표를 쪽 좌표로 바꿈). 표 칸 나누기는 하지 않는다.
- **docx**(`docx_reader`): 그림 단락(`w:drawing`의 `a:blip r:embed`)의 그림을 꺼내 OCR하고, 읽은 줄을 그 그림 단락 **바로 뒤** 단락으로 더한다. 그림 단락 자체는 지금처럼 그림 위치로만 기록.
- OCR 블록은 `Block.ocr = True`.
- **[구현 때 바뀜]** 그림 설명("Fig. …") 찾기가 그림 단락 바로 뒤 단락을 보던 것을, 사이에 낀 OCR 단락은 건너뛰고 보게 고쳤다(OCR 단락이 그림과 설명 사이에 들어가서).

### 3. 저장 표시
- 추출(`extract`): OCR 블록에서 나온 후보는 `extracted_by = "OCR"`. 마이그레이션 **0037**: `requirement.extracted_by` 제약에 `OCR`.
- 신뢰도: OCR 후보 0.5(규칙 1.0, AI 0.7).
- 문서: OCR 블록이 하나라도 있으면 `needs_review = true`. 분류의 판독 가능 여부는 OCR 블록까지 센다(스캔 PDF가 판독 가능이 됨).
- 문서 표 응답에 `ocr_lines`(OCR로 읽은 줄 수) [제안] — 화면 표시는 화면 작업에서.

### 4. 설치
- `backend/Dockerfile`: `apt-get install -y tesseract-ocr tesseract-ocr-kor`.
- CI(`.github/workflows/ci.yml`) backend 작업: 같은 apt 설치 단계. 로컬 개발자는 `brew install tesseract tesseract-lang`(README).
- 상태 점검: `ocr_available`, `ocr_engine`(판). 키·경로는 돌려주지 않는다.

### 5. 시험 자료
- Pillow로 흰 바탕에 큰 글씨 문장을 그린 PNG → reportlab으로 그림만 든 PDF, python-docx로 그림이 든 docx. OCR이 정확히 읽도록 글씨는 크게(28 pt 이상), 기본 글꼴.

## 대안
- AI 비전(Gemini)으로 읽기: 원문 외부 전송, 숫자를 AI가 만듦(CR-01·04). 버림.
- PaddleOCR·EasyOCR: 모델이 크고(수백 MB) 설치가 무거움. Tesseract로 시작.

## 위험
- 스캔 품질이 낮으면 글자가 틀릴 수 있다 → 신뢰도 기준·"OCR" 표시·확인 필요로 사람이 본다.
- 처리 시간: 쪽마다 수 초. 스캔 쪽이 많은 문서는 느려진다 [확인 필요].

## 구현 때 알게 된 것
- 실제 파일 8(Specification No. RFP08, 115 kV 차단기)은 "이미지가 지워져 시험 대상 없음"으로 알려져 있었으나, 실제로는 **쪽이 스캔 그림으로 들어 있었고 OCR로 본문이 읽힌다**("115 KV AC POWER GAS CIRCUIT BREAKERS", "1.1 This specification covers …"). 그래서 document-intake "문서 분류"의 "이미지만 있는 문서" Scenario를 "OCR 엔진 없이"로 좁히고 "OCR로 읽은 이미지 문서" Scenario를 더했다(MODIFIED). 실제 문서 테스트(test_corpus)도 두 경우로 나눴다.
