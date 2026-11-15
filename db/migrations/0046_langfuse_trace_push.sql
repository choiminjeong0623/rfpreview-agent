-- 검토 실행 작업이 끝날 때 AI 호출 기록을 Langfuse로 보낸 결과 (add-langfuse-trace-push).
-- RFP_LANGFUSE_RECORD=on일 때만. 보낸 시각, 이번 작업 trace 화면 주소, 보내지 못한 이유
ALTER TABLE review_run
  ADD COLUMN langfuse_sent_at TIMESTAMPTZ,
  ADD COLUMN langfuse_url TEXT,
  ADD COLUMN langfuse_error VARCHAR(300);
