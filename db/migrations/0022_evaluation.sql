-- 정답지·채점 (change add-evaluation, SCR-19). 정답지는 유형 정답 줄, 채점 기록은 검토 묶음마다.
CREATE TABLE answer_key (
  key_id      SERIAL PRIMARY KEY,
  key_name    VARCHAR(100) NOT NULL UNIQUE,
  key_kind    VARCHAR(10) NOT NULL DEFAULT 'TYPE' CHECK (key_kind IN ('TYPE')),
  made_by     VARCHAR(20) NOT NULL CHECK (made_by IN ('CLAUDE_DRAFT', 'HUMAN')),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE answer_key_row (
  key_id        INT NOT NULL REFERENCES answer_key(key_id) ON DELETE CASCADE,
  row_no        INT NOT NULL,
  text_raw      TEXT NOT NULL,
  context       TEXT,
  expected      VARCHAR(20) NOT NULL,           -- 유형 코드 또는 NONE
  ambiguous     BOOLEAN NOT NULL DEFAULT FALSE,
  human_checked BOOLEAN NOT NULL DEFAULT FALSE, -- 사람이 확인한 줄
  note          TEXT,
  PRIMARY KEY (key_id, row_no)
);

CREATE TABLE eval_score (
  score_id      SERIAL PRIMARY KEY,
  run_ids       INT[] NOT NULL,
  key_id        INT REFERENCES answer_key(key_id) ON DELETE SET NULL,
  metrics       JSONB NOT NULL,
  note          TEXT,                            -- 무엇을 고쳤나
  code_version  VARCHAR(40),
  scored_by     INT REFERENCES app_user(user_id),
  scored_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
