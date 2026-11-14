-- 프롬프트 품질 평가 (add-prompt-eval, FR-18·NFR-13). 평가셋을 역할 함수에 그대로 묻고 코드로 채점한 기록.
-- 기존 eval_score(판정 결과 K지표)와 재는 대상이 다르다(프롬프트).
CREATE TABLE prompt_eval_run (
  eval_id          SERIAL PRIMARY KEY,
  set_name         VARCHAR(100) NOT NULL,
  set_version      VARCHAR(20) NOT NULL,              -- 평가셋 파일 sha256 앞 12자
  model            VARCHAR(100),
  ai_mode          VARCHAR(10) NOT NULL,              -- GEMINI / LOCAL / OFF
  prompt_versions  JSONB NOT NULL,                    -- 역할 → 판
  code_version     VARCHAR(40),
  repeat           INT NOT NULL DEFAULT 1,
  status           VARCHAR(10) NOT NULL CHECK (status IN ('DONE', 'SKIPPED', 'FAILED')),
  skip_reason      TEXT,
  metrics          JSONB NOT NULL DEFAULT '{}',       -- {역할: {지표: {by_source, basis, min, max, mean}}}
  injection_effect INT NOT NULL DEFAULT 0,
  calls            INT NOT NULL DEFAULT 0,
  input_tokens     INT NOT NULL DEFAULT 0,
  output_tokens    INT NOT NULL DEFAULT 0,
  cost_krw         INT,                               -- 팀 가정 단가로 어림. 모르는 모델이면 비움
  seconds          REAL,
  is_baseline      BOOLEAN NOT NULL DEFAULT FALSE,
  note             TEXT,
  run_by           VARCHAR(100),
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- 같은 평가셋에 기준선은 하나만
CREATE UNIQUE INDEX prompt_eval_run_baseline ON prompt_eval_run (set_name) WHERE is_baseline;

CREATE TABLE prompt_eval_item (
  eval_id    INT NOT NULL REFERENCES prompt_eval_run(eval_id) ON DELETE CASCADE,
  repeat_no  INT NOT NULL,                            -- 1부터
  item_id    VARCHAR(100) NOT NULL,
  role       VARCHAR(20) NOT NULL,
  made_by    VARCHAR(20) NOT NULL CHECK (made_by IN ('HUMAN', 'CODE', 'CLAUDE_DRAFT')),
  ok         BOOLEAN,                                 -- NULL = 답 없음
  answer     JSONB,
  error      TEXT,
  PRIMARY KEY (eval_id, repeat_no, item_id)
);
