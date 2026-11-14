-- OCR — 스캔 PDF와 그림 속 글자 읽기 (add-ocr). OCR 줄에서 나온 요구사항의 추출 방법, 문서의 OCR 줄 수
ALTER TABLE requirement DROP CONSTRAINT requirement_extracted_by_check;
ALTER TABLE requirement ADD CONSTRAINT requirement_extracted_by_check
  CHECK (extracted_by IN ('RULE', 'AI', 'OCR'));
ALTER TABLE document
  ADD COLUMN ocr_lines INTEGER NOT NULL DEFAULT 0;   -- OCR로 읽은 줄 수 (0이면 OCR 안 씀)
