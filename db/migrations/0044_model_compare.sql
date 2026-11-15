-- 여러 회사 모델 비교 평가 (add-model-compare, FR-23). 같은 --models 실행은 같은 비교 묶음 번호.
-- ai_mode 칸에는 공급자를 대문자로(GEMINI / ANTHROPIC / OPENAI / LOCAL). 예전 기록은 provider가 비어 있다.
ALTER TABLE prompt_eval_run ADD COLUMN compare_id INT;
ALTER TABLE prompt_eval_run ADD COLUMN provider VARCHAR(20);
ALTER TABLE prompt_eval_run ADD COLUMN latency_p50_ms INT;   -- 문항 응답 시간 (모든 반복·문항, nearest-rank)
ALTER TABLE prompt_eval_run ADD COLUMN latency_p95_ms INT;
CREATE SEQUENCE prompt_eval_compare_seq;
CREATE INDEX prompt_eval_run_compare ON prompt_eval_run (compare_id) WHERE compare_id IS NOT NULL;
