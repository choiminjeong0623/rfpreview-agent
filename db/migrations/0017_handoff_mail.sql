-- 협조 요청 메일 발송 (update-role-handoff-mail, FR-11)
-- 상태 뜻: TODO 안 보냄 / DOING 메일 보냄(시스템이 기록) / DONE 회신 받음(엔지니어가 기록)
-- sent_at은 할 일을 만든 시각으로 이미 쓰므로 메일 보낸 시각은 mail_sent_at에 둔다.
ALTER TABLE assignment ADD COLUMN mail_sent_at TIMESTAMPTZ;
ALTER TABLE assignment ADD COLUMN mail_to TEXT;                      -- 보낸 부서 주소
ALTER TABLE assignment ADD COLUMN sent_by INT REFERENCES app_user(user_id);
ALTER TABLE assignment ADD COLUMN mail_error TEXT;                   -- 주소 없음·발송 실패
ALTER TABLE assignment ADD COLUMN replied_at TIMESTAMPTZ;
ALTER TABLE assignment ADD COLUMN replied_by INT REFERENCES app_user(user_id);
ALTER TABLE assignment ADD COLUMN reply_note TEXT;

-- 발송(SEND)과 회신 기록(REPLY)도 이력에 남긴다
ALTER TABLE review_log DROP CONSTRAINT review_log_action_check;
ALTER TABLE review_log ADD CONSTRAINT review_log_action_check
  CHECK (action IN ('CONFIRM','EDIT','REJECT','ADOPT','DISCARD','UNDO','SEND','REPLY'));
