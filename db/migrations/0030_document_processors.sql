-- 문서 종류별 처리기와 처리 뒤 점검 (add-document-processors, C1)
ALTER TABLE document
  ADD COLUMN processor     VARCHAR(30),                      -- 마지막에 쓴 처리기 (GENERAL = 일반)
  ADD COLUMN process_check TEXT,                             -- 처음 점검에 걸린 이유 (통과면 NULL)
  ADD COLUMN reprocessed   BOOLEAN NOT NULL DEFAULT FALSE;   -- 점검 뒤 일반 처리기로 다시 처리함
