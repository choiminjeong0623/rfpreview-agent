-- AI 설명 문장(claim)과 그 근거 (환각 방지, add-claim-evidence).
-- 문장마다 원문 인용과 근거 위치(source_location)를 남겨, 설명이 어디서 왔는지 되짚을 수 있게 한다.
-- target_table·target_id: 설명이 붙은 결과 (지금은 risk_flag만).
CREATE TABLE claim_evidence (
  claim_id BIGSERIAL PRIMARY KEY,
  run_id INT NOT NULL REFERENCES review_run(run_id),
  target_table VARCHAR(40) NOT NULL,
  target_id INT NOT NULL,
  claim_type VARCHAR(30) NOT NULL,
  claim_text TEXT NOT NULL,
  exact_quote TEXT NOT NULL,
  relation VARCHAR(20) NOT NULL
    CHECK (relation IN ('DIRECT', 'DERIVED', 'INFERRED')),
  status VARCHAR(20) NOT NULL DEFAULT 'NEEDS_REVIEW'
    CHECK (status IN ('SUPPORTED', 'PARTIAL', 'UNSUPPORTED',
                      'CONTRADICTORY', 'NEEDS_REVIEW')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE claim_evidence_source (
  claim_id BIGINT NOT NULL REFERENCES claim_evidence(claim_id) ON DELETE CASCADE,
  location_id INT NOT NULL REFERENCES source_location(location_id),
  source_seq INT NOT NULL DEFAULT 1,
  PRIMARY KEY (claim_id, location_id),
  UNIQUE (claim_id, source_seq)
);
