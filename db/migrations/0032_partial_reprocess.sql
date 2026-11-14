-- 점검에서 떨어진 부분만 다시 묻기 (update-partial-reprocess, C1)
-- processor는 이제 처음 고른 처리기를 그대로 남기고, reprocessed는 실제로 다시 물었을 때만 true
ALTER TABLE document
  ADD COLUMN reprocessed_lines INTEGER NOT NULL DEFAULT 0;  -- 점검 뒤 일반 처리기로 다시 물은 줄 수
