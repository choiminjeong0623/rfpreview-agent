-- 검토 취소와 다시 시도 (add-run-control).
-- 취소는 요청만 적고, 처리 흐름이 다음 진행 기록 때 이 칸을 보고 멈춘다. 멈춘 검토는 FAILED.
-- 0017은 협조 메일(update-role-handoff-mail)에 남겨 둔다.
ALTER TABLE review_run
  ADD COLUMN cancel_requested_at TIMESTAMPTZ,
  ADD COLUMN cancel_requested_by INT REFERENCES app_user(user_id),
  ADD COLUMN retry_count INT NOT NULL DEFAULT 0;
