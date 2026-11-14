-- 요구사항 정답지 (add-requirement-answer-key, B1). 요구사항·위험 조건 정답 줄로 K1·K2·K3·K10을 잰다.
ALTER TABLE answer_key DROP CONSTRAINT IF EXISTS answer_key_key_kind_check;
ALTER TABLE answer_key ADD CONSTRAINT answer_key_key_kind_check CHECK (key_kind IN ('TYPE', 'REQ'));
ALTER TABLE answer_key DROP CONSTRAINT IF EXISTS answer_key_made_by_check;
ALTER TABLE answer_key ADD CONSTRAINT answer_key_made_by_check
  CHECK (made_by IN ('CLAUDE_DRAFT', 'HUMAN', 'AUTO'));      -- AUTO: 코드가 만든 정답(사람 확인 전)
ALTER TABLE answer_key ADD COLUMN doc_name VARCHAR(400);      -- 대상 문서 이름 (파일 이름에 든 글자)

ALTER TABLE answer_key_row ADD COLUMN value_raw TEXT;         -- 정답 값 (K3)
ALTER TABLE answer_key_row ADD COLUMN unit_raw VARCHAR(40);   -- 정답 단위 (환산하지 않음)

ALTER TABLE eval_score ADD COLUMN req_key_id INT REFERENCES answer_key(key_id) ON DELETE SET NULL;
