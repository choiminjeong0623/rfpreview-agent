-- AI 호출 기록 (add-ai-call-trace, FR-21·NFR-14)
-- AI 문장 요청 한 번(재시도 포함)마다 한 줄. 원문은 기본으로 두지 않고 해시만 (NFR-06·07)
CREATE TABLE ai_call (
  call_id         BIGSERIAL PRIMARY KEY,
  run_id          INT REFERENCES review_run(run_id),   -- 분석 밖(평가 등)은 비울 수 있음
  run_token       UUID,                                -- 실행 토큰 (add-run-queue)
  feature         VARCHAR(20) NOT NULL,                -- analysis · assistant · handoff · eval
  step            VARCHAR(20),                         -- 처리 단계 (documents·risks·outputs …)
  role            VARCHAR(12),                         -- AI 역할 (classify·label·type·risk …)
  model           VARCHAR(100),
  prompt_version  VARCHAR(10),
  attempt         INT NOT NULL,                        -- 0 = 첫 시도, 1·2 = 재시도
  started_at      TIMESTAMPTZ NOT NULL,
  ended_at        TIMESTAMPTZ NOT NULL,
  duration_ms     INT NOT NULL,
  input_tokens    INT NOT NULL DEFAULT 0,
  output_tokens   INT NOT NULL DEFAULT 0,
  thinking_tokens INT NOT NULL DEFAULT 0,
  result          VARCHAR(16) NOT NULL
                    CHECK (result IN ('OK', 'FORMAT_ERROR', 'CONFIG_ERROR', 'TIMEOUT',
                                      'CONNECTION_ERROR')),
  dropped_reason  VARCHAR(40),                         -- 코드 검사에서 버린 이유
  input_hash      CHAR(16) NOT NULL,                   -- sha256(프롬프트 + 답 형식) 앞 16자
  output_hash     CHAR(16),                            -- sha256(답 JSON) 앞 16자
  batch_lines     INT NOT NULL DEFAULT 0
);
CREATE INDEX ai_call_run ON ai_call (run_id, call_id);
CREATE INDEX ai_call_input ON ai_call (input_hash);

-- 원문: RFP_TRACE_RAW=on일 때만, 7일 뒤 지운다 (호출 기록은 남음)
CREATE TABLE ai_call_raw (
  call_id     BIGINT PRIMARY KEY REFERENCES ai_call(call_id) ON DELETE CASCADE,
  prompt      TEXT NOT NULL,
  answer      TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
