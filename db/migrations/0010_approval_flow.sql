-- 결재 흐름(update-approval-flow): 결재자를 골라 상신하고, 결정 전에는 상신을 취소할 수 있다

-- 상신한 사람, 상신 의견, 취소 시각. approver_id는 상신할 때 지정 결재자로 채운다
ALTER TABLE approval ADD COLUMN requested_by INT REFERENCES app_user(user_id);
ALTER TABLE approval ADD COLUMN request_comment TEXT;
ALTER TABLE approval ADD COLUMN withdrawn_at TIMESTAMPTZ;

ALTER TABLE approval DROP CONSTRAINT approval_decision_check;
ALTER TABLE approval ADD CONSTRAINT approval_decision_check
  CHECK (decision IN ('APPROVED','REJECTED','WITHDRAWN'));

-- 지금 열려 있는 승인 대기는 결재자가 비어 있으므로 기본 승인자로 채운다
UPDATE approval SET approver_id = (SELECT min(user_id) FROM app_user WHERE role = 'APPROVER')
WHERE decision IS NULL AND approver_id IS NULL;
