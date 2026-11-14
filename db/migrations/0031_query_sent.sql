-- 질의 보냄 표시 (add-query-sent, 결정 Q4). 질의 후보 판정에 엔지니어가 고객에게 질의를 보냈다고 표시한다.
-- 되돌리면 둘 다 NULL. 고객 회신 내용은 저장하지 않는다.
ALTER TABLE judgment
  ADD COLUMN query_sent_at TIMESTAMPTZ,
  ADD COLUMN query_sent_by INT REFERENCES app_user(user_id);

-- 이력 동작에 질의 보냄·되돌리기를 더한다
ALTER TABLE review_log DROP CONSTRAINT review_log_action_check;
ALTER TABLE review_log ADD CONSTRAINT review_log_action_check
  CHECK (action IN ('CONFIRM','EDIT','REJECT','ADOPT','DISCARD','UNDO','SEND','REPLY','ADD',
                    'QUERY_SENT','QUERY_UNSENT'));
