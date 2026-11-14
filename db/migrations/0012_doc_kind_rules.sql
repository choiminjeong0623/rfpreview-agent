-- 문서 종류 규칙 사전 (update-doc-kind-rules). 코드에 있던 파일명·첫 장 표현을 data/seed/doc_kind_rules.csv에서 적재한다.
-- 위에서부터(priority 작은 것부터) 먼저 맞는 줄의 문서 종류를 쓴다. 파일 이름 표현을 모두 본 뒤 첫 장 표현을 본다.
CREATE TABLE doc_kind_rule (
  doc_kind_rule_id SERIAL PRIMARY KEY,
  priority        INT NOT NULL UNIQUE,
  doc_kind        VARCHAR(30) NOT NULL CHECK (doc_kind IN
                   ('BID_FORM','REQUIREMENT_SPEC','PURCHASE_SPEC','TEST_SPEC','SUPPLIER_SPEC')),
  name_pattern    TEXT NOT NULL,                    -- 소문자 파일 이름에서 찾는 정규식
  page_pattern    TEXT,                             -- 첫 장에서 찾는 정규식 (대소문자 무시). 없으면 파일 이름만
  note            TEXT
);
