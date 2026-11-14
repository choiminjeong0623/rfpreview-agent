-- 단계부터 다시 처리 (add-step-rewind, C2). 이력 동작에 REWIND(단계·사유)를 더한다
ALTER TABLE review_log DROP CONSTRAINT review_log_action_check;
ALTER TABLE review_log ADD CONSTRAINT review_log_action_check
  CHECK (action IN ('CONFIRM','EDIT','REJECT','ADOPT','DISCARD','UNDO','SEND','REPLY','ADD',
                    'QUERY_SENT','QUERY_UNSENT','REWIND'));
