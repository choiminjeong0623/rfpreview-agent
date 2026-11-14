-- 위험 표현 사전에 추가 제안 (change add-rule-suggestion, FR-06 ④). 규칙 담당이 반영하면 rule_edit에 남는다.
CREATE TABLE rule_suggestion (
  suggestion_id   SERIAL PRIMARY KEY,
  dictionary      VARCHAR(20) NOT NULL DEFAULT 'risk-expressions'
                  CHECK (dictionary IN ('risk-expressions')),
  expression      VARCHAR(100) NOT NULL,
  note            TEXT,
  run_id          INT NOT NULL REFERENCES review_run(run_id),
  requirement_id  INT NOT NULL REFERENCES requirement(requirement_id),  -- 표현이 나온 첫 문장 (원문 위치)
  status          VARCHAR(10) NOT NULL DEFAULT 'PENDING'
                  CHECK (status IN ('PENDING', 'ACCEPTED', 'DECLINED')),
  suggested_by    INT NOT NULL REFERENCES app_user(user_id),
  suggested_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  decided_by      INT REFERENCES app_user(user_id),
  decided_at      TIMESTAMPTZ,
  decision_reason TEXT,
  edit_id         INT REFERENCES rule_edit(edit_id)
);
CREATE INDEX ix_rule_suggestion_run ON rule_suggestion (run_id);
-- 확인 대기 중인 같은 표현은 하나만
CREATE UNIQUE INDEX ux_rule_suggestion_pending ON rule_suggestion (lower(expression))
  WHERE status = 'PENDING';
