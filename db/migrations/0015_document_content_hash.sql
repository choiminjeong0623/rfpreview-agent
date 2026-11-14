-- 같은 파일 번호라도 내용이 다른 파일은 다른 문서로 처리한다.
-- 이전에는 파일 번호 + 처리 판만 보고 결과를 다시 써서, 이름이 같은 다른 판 파일(고친 RFP)이 예전 분석 결과를 받았다.
-- 이 칸이 빈 예전 문서 행은 다시 쓰지 않는다 (다음 실행 때 새로 처리).
ALTER TABLE document ADD COLUMN content_hash CHAR(64);           -- 원본 파일 SHA-256
DROP INDEX ux_document_version;
CREATE UNIQUE INDEX ux_document_version ON document (file_no, processing_key, COALESCE(content_hash, ''));
