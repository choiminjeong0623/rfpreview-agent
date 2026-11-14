-- 분석 밖 AI 사용량 (add-ai-usage-log). 분석 실행의 사용량은 review_run에 그대로 둔다.
CREATE TABLE ai_usage (
  usage_id        BIGSERIAL PRIMARY KEY,
  used_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  feature         VARCHAR(20) NOT NULL CHECK (feature IN ('ASSISTANT', 'HANDOFF_ASK',
                    'PRODUCT_SWITCH', 'LOSS_EDIT', 'REVIEW_ACTION', 'BULK_CONFIRM')),
  run_id          INTEGER REFERENCES review_run (run_id) ON DELETE SET NULL,
  model           VARCHAR(60),
  calls           INTEGER NOT NULL,
  retries         INTEGER NOT NULL DEFAULT 0,
  input_tokens    BIGINT NOT NULL DEFAULT 0,
  output_tokens   BIGINT NOT NULL DEFAULT 0,
  thinking_tokens BIGINT NOT NULL DEFAULT 0
);
CREATE INDEX ix_ai_usage_used_at ON ai_usage (used_at);
