-- 뜻으로 찾기 (add-meaning-search, B3·B4·B5). 문장 벡터는 글자 해시로 한 번만 받아 다시 쓴다.
CREATE TABLE text_vector (
  model      VARCHAR(60) NOT NULL,
  text_hash  CHAR(64) NOT NULL,          -- 공백을 정리한 원문의 sha256
  vec        REAL[] NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (model, text_hash)
);

-- 검토마다 뜻 찾기 후보. RISK_SENTENCE = 사전 추가 후보(B5), ITEM_LINK = 항목 연결 후보(B3)
CREATE TABLE meaning_candidate (
  candidate_id    SERIAL PRIMARY KEY,
  run_id          INT NOT NULL REFERENCES review_run(run_id) ON DELETE CASCADE,
  kind            VARCHAR(20) NOT NULL CHECK (kind IN ('RISK_SENTENCE', 'ITEM_LINK')),
  requirement_id  INT NOT NULL REFERENCES requirement(requirement_id),  -- 원문 위치
  text_raw        TEXT NOT NULL,          -- 후보 글 (문장 또는 표 항목 이름)
  near_text       TEXT NOT NULL,          -- 가장 가까운 문장·표현
  target          VARCHAR(40),            -- ITEM_LINK: 항목키 / RISK_SENTENCE: 가까운 위험 조건 종류
  score           NUMERIC(4,3) NOT NULL,
  second_target   VARCHAR(40),
  second_score    NUMERIC(4,3),
  status          VARCHAR(10) NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'ACCEPTED', 'HIDDEN')),
  decided_by      INT REFERENCES app_user(user_id),
  decided_at      TIMESTAMPTZ
);
CREATE INDEX ix_meaning_candidate_run ON meaning_candidate (run_id, kind);
