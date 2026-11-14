-- 검토에 문서 더하기 (add-document-addendum, FR-01 ⑤): 정정본·추가 문서를 더한 일을 이력에 남긴다.
-- target_table = 'run_document', target_id = run_id, after_value = {"files": [...]}.
ALTER TABLE review_log DROP CONSTRAINT review_log_action_check;
ALTER TABLE review_log ADD CONSTRAINT review_log_action_check
  CHECK (action IN ('CONFIRM','EDIT','REJECT','ADOPT','DISCARD','UNDO','SEND','REPLY','ADD'));
