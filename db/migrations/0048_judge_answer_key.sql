-- 판정 정답지 (add-eval-demo). 판정 정답 줄로 K5-정답지·K6-정답지를 잰다.
ALTER TABLE answer_key DROP CONSTRAINT IF EXISTS answer_key_key_kind_check;
ALTER TABLE answer_key ADD CONSTRAINT answer_key_key_kind_check
  CHECK (key_kind IN ('TYPE', 'REQ', 'JUDGE'));

ALTER TABLE answer_key_row ADD COLUMN product_code VARCHAR(40);  -- 정답 비교 제품 (비면 보지 않음)

ALTER TABLE eval_score ADD COLUMN judge_key_id INT REFERENCES answer_key(key_id) ON DELETE SET NULL;
