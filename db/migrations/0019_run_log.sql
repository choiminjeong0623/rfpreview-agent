-- 실행 기록 (add-run-log, NFR-09): 검토마다 AI 사용량과 단계별 걸린 시간.
-- 비용은 저장하지 않고 화면에 낼 때 모델 단가(팀 가정)로 계산한다.
ALTER TABLE review_run
  ADD COLUMN llm_calls INT NOT NULL DEFAULT 0,             -- 언어 모델 요청 수 (재시도 포함)
  ADD COLUMN llm_retries INT NOT NULL DEFAULT 0,           -- 그중 재시도 (CR-12)
  ADD COLUMN llm_input_tokens BIGINT NOT NULL DEFAULT 0,
  ADD COLUMN llm_output_tokens BIGINT NOT NULL DEFAULT 0,
  ADD COLUMN llm_thinking_tokens BIGINT NOT NULL DEFAULT 0,
  ADD COLUMN documents_reused INT NOT NULL DEFAULT 0;      -- 이전 처리 결과를 다시 쓴 문서 수 (NFR-05)

-- 단계마다 시작·끝 시각. attempt는 다시 시도 횟수(review_run.retry_count)와 같다.
CREATE TABLE run_step_time (
  run_id INT NOT NULL REFERENCES review_run(run_id),
  attempt INT NOT NULL,
  step VARCHAR(20) NOT NULL,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  PRIMARY KEY (run_id, attempt, step)
);
