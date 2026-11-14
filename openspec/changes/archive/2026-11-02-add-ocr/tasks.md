## 1. 엔진 (BE 나송주)
- [x] 1.1 `uv add pytesseract`, `pipeline/ocr.py`(사용 가능·엔진 판·그림 → 줄, 신뢰도 기준), 설정 `RFP_OCR`
- [x] 1.2 처리 판에 OCR 엔진 판

## 2. 읽기와 저장 (BE 나송주)
- [x] 2.1 PDF 글자 없는 쪽 OCR, docx 그림 OCR(그림 단락 뒤 단락), `Block.ocr`
- [x] 2.2 추출 `extracted_by=OCR`·신뢰도 0.5, 문서 확인 필요, 마이그레이션 0037, 문서 표 `ocr_lines`
- [x] 2.3 상태 점검 `ocr_available`·`ocr_engine`, 스키마, `npm run gen:api`

## 3. 설치 (나송주)
- [x] 3.1 backend Dockerfile·CI에 Tesseract(eng·kor), README 로컬 설치

## 4. 시험과 마무리 (나송주)
- [x] 4.1 Scenario마다 테스트(`tests/test_ocr.py`)
- [x] 4.2 AGENTS.md 표, 추적표, archive
