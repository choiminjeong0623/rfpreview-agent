-- 판정 규칙 화면에서 규칙 사전 고치기 (add-rule-editing). DB가 원본이고 CSV는 시작값이다.

-- 화면에서 고친 기록. 사전을 다시 적재하면 버리지 않은 고침을 edit_id 순서로 다시 적용한다.
CREATE TABLE rule_edit (
  edit_id         SERIAL PRIMARY KEY,
  dictionary      VARCHAR(20) NOT NULL CHECK (dictionary IN ('compare','risk-expressions','items','doc-kinds')),
  row_key         JSONB NOT NULL,                   -- 고치기 전 줄의 자연 키 (추가면 새 줄의 키)
  action          VARCHAR(6) NOT NULL CHECK (action IN ('ADD','EDIT','DELETE')),
  before_value    JSONB,
  after_value     JSONB,
  reason          TEXT NOT NULL,
  actor_id        INT NOT NULL REFERENCES app_user(user_id),
  edited_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  discarded_at    TIMESTAMPTZ                       -- rfp-db seed-rules --reset-edits로 버린 시각
);
CREATE INDEX ix_rule_edit_dictionary ON rule_edit (dictionary, edited_at);

-- 지난 검토 결과가 가리키는 줄은 지우지 않고 끈다. 꺼진 줄은 새 검토에 쓰지 않는다.
ALTER TABLE compare_rule ADD COLUMN active BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE risk_expression ADD COLUMN active BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE item_key ADD COLUMN active BOOLEAN NOT NULL DEFAULT TRUE;
