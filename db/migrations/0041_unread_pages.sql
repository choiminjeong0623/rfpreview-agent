-- 읽지 못한 쪽 알림 (add-unread-pages, FR-19·CR-13·AR-09)
-- PDF를 읽는 그 자리에서 쪽마다 읽음·빈 쪽·읽지 못함과 이유를 남긴다. docx는 쪽이 없어 비운다.
ALTER TABLE document
  ADD COLUMN page_count   INT,
  ADD COLUMN pages_read   INT,
  ADD COLUMN pages_blank  INT,
  ADD COLUMN unread_pages JSONB;    -- [{page, reason, dropped, dropped_conf}] (쪽 순서)

-- 그림을 OCR로 읽지 못한 이유 (docx 그림, PDF 글자 쪽 속 큰 그림)
ALTER TABLE doc_figure
  ADD COLUMN ocr_reason VARCHAR(16)
    CHECK (ocr_reason IN ('OCR_OFF', 'OCR_MISSING', 'OCR_LOW_CONF', 'OCR_EMPTY'));

INSERT INTO approval_rule (ar_code, description, threshold)
VALUES ('AR-09', '사람이 확인하지 않은 읽지 못한 쪽이 남아 있음 (상신은 막지 않음)', NULL)
ON CONFLICT (ar_code) DO NOTHING;
