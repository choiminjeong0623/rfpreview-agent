-- PDF 문서 읽기 (add-pdf-input). 줄 번호 기준에 PDF(쪽마다 글자 줄·표 행을 이어 센 줄)를 더한다
ALTER TABLE document DROP CONSTRAINT document_line_basis_check;
ALTER TABLE document ADD CONSTRAINT document_line_basis_check
  CHECK (line_basis IN ('TXT', 'DOCX', 'PDF'));
