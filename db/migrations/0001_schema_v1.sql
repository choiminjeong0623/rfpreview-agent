-- =====================================================================
-- RFP 기술 검토·견적 지원 AI 시스템 — DB 스키마 초안 v1 (PostgreSQL 16)
-- 근거: 기능 요구사항 명세서 v1 (2026-10-23), 프로젝트 기획서 v1.4
-- 상태: 클로드 초안. DB 담당 검토 전
-- 영역: ① 문서·구조  ② 요구사항·값  ③ 사전(규칙)  ④ 제품·현장 이력
--       ⑤ 검토 실행·결과  ⑥ 확인·승인·전달
-- =====================================================================

-- ---------------------------------------------------------------------
-- ① 문서·구조 (FR-01, FR-02)
-- ---------------------------------------------------------------------
CREATE TABLE project (                       -- 사업. 값 불일치 비교 범위의 기준 (FR-06)
  project_id      SERIAL PRIMARY KEY,
  project_name    VARCHAR(200) NOT NULL,
  is_confirmed    BOOLEAN NOT NULL DEFAULT FALSE,   -- 파일 3~8 묶음은 운영진 확인 전(Q5)
  note            TEXT
);

CREATE TABLE document (                      -- RFP 파일 1개 (FR-01)
  document_id     SERIAL PRIMARY KEY,
  file_no         SMALLINT NOT NULL UNIQUE,         -- 1~22
  file_name       VARCHAR(400) NOT NULL,
  bundle          CHAR(1) NOT NULL CHECK (bundle IN ('A','B','C','D')),
  doc_kind        VARCHAR(30) NOT NULL CHECK (doc_kind IN
                   ('BID_FORM','REQUIREMENT_SPEC','PURCHASE_SPEC','TEST_SPEC','SUPPLIER_SPEC','UNKNOWN')),
  project_id      INT REFERENCES project(project_id),   -- 확인 전이면 NULL
  language        VARCHAR(10) NOT NULL,             -- en / ko / image
  standard_system VARCHAR(20) CHECK (standard_system IN ('IEC','IEEE_UL','KS_ES','MIXED')),
  judge_target    BOOLEAN NOT NULL,                 -- 묶음 A·B만 TRUE (CR-09)
  readable        BOOLEAN NOT NULL DEFAULT TRUE,    -- 파일 8은 FALSE
  classify_by     VARCHAR(10) NOT NULL CHECK (classify_by IN ('RULE','AI','HUMAN')),
  needs_review    BOOLEAN NOT NULL DEFAULT FALSE    -- 규칙과 AI 판단이 다를 때
);

CREATE TABLE document_pair (                 -- 원본·정정본 쌍 (FR-01)
  pair_id         SERIAL PRIMARY KEY,
  document_id_a   INT NOT NULL REFERENCES document(document_id),
  document_id_b   INT NOT NULL REFERENCES document(document_id),
  relation        VARCHAR(20) NOT NULL CHECK (relation IN ('REVISION','DUPLICATE_CONTENT')),
  status          VARCHAR(10) NOT NULL CHECK (status IN ('CANDIDATE','CONFIRMED','REJECTED')),
  evidence        TEXT,                             -- 예: 데이터시트 항목 881개 공유
  CHECK (document_id_a <> document_id_b)
);

CREATE TABLE section (                       -- 장·절·항 (FR-02)
  section_id      SERIAL PRIMARY KEY,
  document_id     INT NOT NULL REFERENCES document(document_id),
  parent_id       INT REFERENCES section(section_id),
  section_no      VARCHAR(40),                      -- "6", "3.2", "가."
  title           TEXT,
  is_toc          BOOLEAN NOT NULL DEFAULT FALSE,   -- 목차 줄
  line_start      INT NOT NULL,
  line_end        INT,
  structure_flag  BOOLEAN NOT NULL DEFAULT FALSE    -- 번호가 끊긴 곳 ("구조 확인 필요")
);

CREATE TABLE doc_table (                     -- 표 (쪽 넘김 표는 하나로 이음)
  table_id        SERIAL PRIMARY KEY,
  document_id     INT NOT NULL REFERENCES document(document_id),
  section_id      INT REFERENCES section(section_id),
  table_name      VARCHAR(100),                     -- 예: TS-115-GIS
  source_table_nos INT[] NOT NULL,                  -- Word 표 번호 목록 (예: {234,235,236,237})
  column_roles    JSONB NOT NULL,                   -- {"0":"ITEM_NO","1":"ITEM_NAME","2":"UNIT","3":"REQUIRED","4":"WARRANTED"}
  role_flag       BOOLEAN NOT NULL DEFAULT FALSE    -- 칸 역할을 못 찾음
);

CREATE TABLE table_row (                     -- 표의 한 행 (반복 머리글은 저장하지 않음)
  row_id          SERIAL PRIMARY KEY,
  table_id        INT NOT NULL REFERENCES doc_table(table_id),
  parent_row_id   INT REFERENCES table_row(row_id), -- 하위 항목(20-1)의 상위
  item_no         VARCHAR(20),                      -- "16", "20-1"
  item_name_raw   TEXT,
  unit_raw        VARCHAR(40),
  required_raw    TEXT,                             -- 발주처 요구값 원문
  warranted_raw   TEXT,                             -- 보증값 칸 원문(대부분 빈칸)
  supplier_mark   CHAR(1) CHECK (supplier_mark IN ('C','D','E')),  -- 파일 18
  line_no         INT NOT NULL,
  row_order       INT NOT NULL
);

CREATE TABLE source_location (               -- 원문 위치 (CR-03). 같은 내용이 여러 곳이면 여러 행
  location_id     SERIAL PRIMARY KEY,
  document_id     INT NOT NULL REFERENCES document(document_id),
  section_id      INT REFERENCES section(section_id),
  row_id          INT REFERENCES table_row(row_id),
  line_start      INT NOT NULL,
  line_end        INT
);

-- ---------------------------------------------------------------------
-- ③ 사전(규칙) — ②보다 먼저 만들어야 FK가 걸림
-- ---------------------------------------------------------------------
CREATE TABLE requirement_type (              -- 유형 7종 (명세서 2-2)
  type_code       VARCHAR(20) PRIMARY KEY,          -- TECH_PERF, RISK, STANDARD_CERT, COST, TEST, MAKER_QUAL, SITE_ENV
  type_name       VARCHAR(40) NOT NULL,
  default_role    VARCHAR(20) NOT NULL              -- 전달받는 역할 (FR-11)
);

CREATE TABLE type_rule (                     -- 유형 규칙표 (FR-04)
  type_rule_id    SERIAL PRIMARY KEY,
  pattern         TEXT NOT NULL,                    -- "Type Test", "ISO", "$/kW"
  type_code       VARCHAR(20) NOT NULL REFERENCES requirement_type(type_code),
  priority        SMALLINT NOT NULL DEFAULT 100
);

CREATE TABLE item_key (                      -- 항목 이름 사전의 표준 항목 (FR-05)
  item_key        VARCHAR(40) PRIMARY KEY,          -- rated_current, gas_leakage_rate ...
  name_ko         VARCHAR(80) NOT NULL,
  default_direction VARCHAR(10) NOT NULL CHECK (default_direction IN ('EQ','GE','LE','LT','IN','FILL','TEXT')),
  strength_direction VARCHAR(10) NOT NULL DEFAULT 'NONE'
                   CHECK (strength_direction IN ('HIGHER','LOWER','NONE')),  -- 강점 방향 (FR-07·14)
  note            TEXT
);

CREATE TABLE item_alias (                    -- 같은 뜻의 원문 표현
  alias_id        SERIAL PRIMARY KEY,
  item_key        VARCHAR(40) NOT NULL REFERENCES item_key(item_key),
  alias_text      VARCHAR(200) NOT NULL,
  UNIQUE (alias_text)
);

CREATE TABLE compare_rule (                  -- 비교 방향 사전 (표·항목 단위 예외 규칙)
  compare_rule_id SERIAL PRIMARY KEY,
  table_name      VARCHAR(100),                     -- TS-115-GIS, TS-SG
  item_no         VARCHAR(20),
  item_key        VARCHAR(40) REFERENCES item_key(item_key),
  direction       VARCHAR(10) NOT NULL CHECK (direction IN ('EQ','GE','LE','LT','IN','FILL','TEXT','AI')),
  time_condition  BOOLEAN NOT NULL DEFAULT FALSE,   -- "더 길면 준수" 규칙 적용 (A-3)
  strength_direction VARCHAR(10) CHECK (strength_direction IN ('HIGHER','LOWER','NONE')),  -- 비우면 item_key 값
  process_note    TEXT
);

CREATE TABLE risk_expression (               -- 위험 표현 사전 (FR-06)
  expr_id         SERIAL PRIMARY KEY,
  expression      VARCHAR(100) NOT NULL,
  language        VARCHAR(5) NOT NULL,
  risk_kind       VARCHAR(20) NOT NULL CHECK (risk_kind IN ('BLANKET','COST_SHIFT','OPEN_SCOPE')),
  context_rule    TEXT NOT NULL                     -- 위험 후보로 보는 조건 (문장 위치)
);

CREATE TABLE column_role_dict (              -- 칸 이름 사전 (FR-02)
  header_text     VARCHAR(100) PRIMARY KEY,         -- "Employer's Requirement"
  column_role     VARCHAR(20) NOT NULL CHECK (column_role IN
                   ('ITEM_NO','ITEM_NAME','UNIT','REQUIRED','WARRANTED','SUPPLIER_MARK'))
);

CREATE TABLE company_fixed_value (           -- 회사 고정값 (FR-08)
  fixed_key       VARCHAR(40) PRIMARY KEY,          -- manufacturer, country_of_origin
  fixed_value     VARCHAR(200) NOT NULL
);

-- ---------------------------------------------------------------------
-- ④ 제품·현장 이력
-- ---------------------------------------------------------------------
CREATE TABLE product_family (
  family          VARCHAR(30) PRIMARY KEY,          -- GIS, MV_EQUIP ...
  family_name     VARCHAR(200) NOT NULL             -- 코드 1개에 이름 1개
);

CREATE TABLE product_master (                -- 26열 + 손실 칸 (기획서 5-3)
  product_code    VARCHAR(40) PRIMARY KEY,
  product_name    VARCHAR(200) NOT NULL,
  family          VARCHAR(30) NOT NULL REFERENCES product_family(family),
  description     TEXT,
  standards       TEXT,
  certifications  TEXT,                             -- 문장 한 칸 (인증서 별도 표는 만들지 않기로 함)
  has_firmware    CHAR(1),
  fw_latest       VARCHAR(20),
  warranty_months SMALLINT,
  lifecycle_status VARCHAR(20) NOT NULL,
  std_lead_time_weeks SMALLINT,
  moq             INT,
  list_price_usd  NUMERIC(14,2),
  weight_kg       NUMERIC(10,2),
  dimensions_mm   VARCHAR(100),
  ip_rating       VARCHAR(40),
  operating_temp  VARCHAR(100),
  tech_support_dept VARCHAR(20),
  doc_ids         TEXT,
  rated_voltage_kv NUMERIC(8,3),
  rated_current_a NUMERIC(10,1),
  short_circuit_ka NUMERIC(8,2),
  is_assumed      CHAR(1) NOT NULL CHECK (is_assumed IN ('Y','N')),
  source_doc      VARCHAR(400) NOT NULL,
  market          VARCHAR(40),
  -- 아래는 이번에 추가 (FR-13)
  rated_frequency VARCHAR(20),                      -- "50/60" — 판정에 자주 쓰여 description에서 분리 [제안]
  is_design_card  BOOLEAN NOT NULL DEFAULT FALSE,   -- GIS-145-P7 같은 설계 사례 카드. 기본 비교 대상 아님
  noload_loss_kw  NUMERIC(10,2),
  load_loss_kw    NUMERIC(10,2),
  aux_loss_kw     NUMERIC(10,2),
  loss_is_assumed BOOLEAN                           -- 손실값이 팀 가정이면 TRUE
);

CREATE TABLE item_pm_mapping (               -- 항목 → product_master 열 연결표 (FR-08)
  item_key        VARCHAR(40) PRIMARY KEY REFERENCES item_key(item_key),
  pm_column       VARCHAR(40),                      -- rated_current_a, weight_kg ...
  fixed_key       VARCHAR(40) REFERENCES company_fixed_value(fixed_key),
  usage           VARCHAR(20) NOT NULL CHECK (usage IN ('COMPARE','FILL','BOTH')),
  CHECK ((pm_column IS NULL) <> (fixed_key IS NULL))  -- 둘 중 하나만
);

CREATE TABLE fault_catalog (                 -- 프로젝트 1 고장 사전 (97종, 사용 허용 시 적재 — Q8)
  fault_id        VARCHAR(20) PRIMARY KEY,          -- FLT-051
  family          VARCHAR(30) NOT NULL,
  applies_to      TEXT,
  symptom         TEXT NOT NULL,
  root_cause      TEXT NOT NULL,
  action          TEXT NOT NULL,
  verified        BOOLEAN NOT NULL DEFAULT FALSE    -- 의도된 오류 여부를 팀이 확인했는지
);

CREATE TABLE resolution_case (               -- 프로젝트 1 해결 사례 (800건)
  case_id         VARCHAR(30) PRIMARY KEY,
  fault_id        VARCHAR(20) NOT NULL REFERENCES fault_catalog(fault_id),
  summary         TEXT,
  prevention      TEXT
);

CREATE TABLE fault_link (                    -- 요구–고장 연결표 (규칙 사전 5번째, 5~10줄)
  fault_link_id   SERIAL PRIMARY KEY,
  item_key        VARCHAR(40) NOT NULL REFERENCES item_key(item_key),
  product_family  VARCHAR(30) NOT NULL REFERENCES product_family(family),
  fault_id        VARCHAR(20) NOT NULL REFERENCES fault_catalog(fault_id),
  confirmed_by    VARCHAR(40) NOT NULL,             -- 팀 확정자
  UNIQUE (item_key, product_family, fault_id)
);

-- ---------------------------------------------------------------------
-- ② 요구사항·값 (FR-03, FR-04, FR-05)
-- ---------------------------------------------------------------------
CREATE TABLE requirement (
  requirement_id  SERIAL PRIMARY KEY,
  document_id     INT NOT NULL REFERENCES document(document_id),
  section_id      INT REFERENCES section(section_id),
  row_id          INT REFERENCES table_row(row_id),  -- 표 칸에서 왔으면
  source_kind     VARCHAR(20) NOT NULL CHECK (source_kind IN ('SENTENCE','TABLE_CELL','SUPPLIER_ANSWER')),
  text_raw        TEXT NOT NULL,
  req_kind        VARCHAR(20) NOT NULL CHECK (req_kind IN ('REQUIREMENT','WRITING_RULE','TOC','HEADER')),
  dedup_of        INT REFERENCES requirement(requirement_id),  -- 같은 문장이 여러 파일에 있을 때 대표 행
  extracted_by    VARCHAR(10) NOT NULL CHECK (extracted_by IN ('RULE','AI')),
  confidence      NUMERIC(3,2),
  is_assumed      BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE requirement_location (          -- 요구사항 ↔ 원문 위치 (N:M)
  requirement_id  INT NOT NULL REFERENCES requirement(requirement_id),
  location_id     INT NOT NULL REFERENCES source_location(location_id),
  PRIMARY KEY (requirement_id, location_id)
);

CREATE TABLE requirement_type_tag (          -- 요구사항 ↔ 유형 (주 1 + 보조 N)
  requirement_id  INT NOT NULL REFERENCES requirement(requirement_id),
  type_code       VARCHAR(20) NOT NULL REFERENCES requirement_type(type_code),
  is_primary      BOOLEAN NOT NULL,
  decided_by      VARCHAR(10) NOT NULL CHECK (decided_by IN ('RULE','AI','HUMAN')),
  type_rule_id    INT REFERENCES type_rule(type_rule_id),
  PRIMARY KEY (requirement_id, type_code)
);
CREATE UNIQUE INDEX ux_type_primary ON requirement_type_tag(requirement_id) WHERE is_primary;

CREATE TABLE req_value (                     -- 값 정리 결과 (FR-05). 요구사항 1개에 값 여러 개 가능
  value_id        SERIAL PRIMARY KEY,
  requirement_id  INT NOT NULL REFERENCES requirement(requirement_id),
  raw_text        TEXT,                             -- 원문 문자열 그대로 ("<0.5")
  cell_form       VARCHAR(10) NOT NULL CHECK (cell_form IN ('EMPTY','NUMBER','FORMULA','DELEGATED','TEXT','YESNO')),
  num_value       NUMERIC(18,6),                    -- 계산식이면 계산 결과
  operator        VARCHAR(2) CHECK (operator IN ('=','<','<=','>','>=')),
  unit_raw        VARCHAR(40),                      -- 원문 단위 (환산하지 않음)
  cond_time_s     NUMERIC(8,2),                     -- 시간 조건 (1 sec → 1)
  cond_raw        TEXT,                             -- 그 밖의 조건 원문
  item_key        VARCHAR(40) REFERENCES item_key(item_key),
  target_object   VARCHAR(100),                     -- 적용 대상 (GIS 전체 / 차단기 / 케이블)
  basis_standard  VARCHAR(100),                     -- 근거 규격
  delegated_std   VARCHAR(100),                     -- 규격 위임이면 규격 이름
  equipment_key   VARCHAR(100),                     -- 문서 간 비교용 "설비 이름 + 설치 장소" (UPS|154kV 변전소)
  project_id      INT REFERENCES project(project_id),  -- document에서 복사 (비교 범위 조회용)
  flag            VARCHAR(30)                       -- UNIT_MISSING, FORMULA_NOT_ALLOWED ...
);

-- ---------------------------------------------------------------------
-- ⑤ 검토 실행·결과 (FR-06 ~ FR-09, FR-12 ~ FR-15)
-- ---------------------------------------------------------------------
CREATE TABLE app_user (
  user_id         SERIAL PRIMARY KEY,
  user_name       VARCHAR(80) NOT NULL,
  role            VARCHAR(20) NOT NULL CHECK (role IN ('ENGINEER','COST','QUALITY','SALES','APPROVER'))
);

CREATE TABLE review_run (                    -- 검토 1회 (LangGraph 실행 단위). 결과는 모두 실행에 묶임
  run_id          SERIAL PRIMARY KEY,
  project_id      INT REFERENCES project(project_id),
  started_by      INT NOT NULL REFERENCES app_user(user_id),
  started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  stage           VARCHAR(20) NOT NULL CHECK (stage IN
                   ('PROCESSING','ENGINEER_REVIEW','APPROVAL','APPROVED','REJECTED','FAILED')),
  dict_version    VARCHAR(20) NOT NULL,             -- 사전·제품표 판 (재현성 CR-11)
  graph_state     JSONB                             -- 흐름 상태 저장
);

CREATE TABLE run_document (                  -- 실행 ↔ 문서
  run_id          INT NOT NULL REFERENCES review_run(run_id),
  document_id     INT NOT NULL REFERENCES document(document_id),
  PRIMARY KEY (run_id, document_id)
);

CREATE TABLE risk_flag (                     -- 위험 조건 후보 (FR-06)
  risk_id         SERIAL PRIMARY KEY,
  run_id          INT NOT NULL REFERENCES review_run(run_id),
  risk_kind       VARCHAR(20) NOT NULL CHECK (risk_kind IN ('BLANKET','VALUE_MISMATCH','OPEN_SCOPE')),
  expr_id         INT REFERENCES risk_expression(expr_id),  -- 표현 사전으로 찾았으면
  explanation_ai  TEXT,                             -- 왜 위험한지 / 왜 다를 수 있는지
  status          VARCHAR(10) NOT NULL CHECK (status IN ('CANDIDATE','CONFIRMED','CLOSED_OK'))
);

CREATE TABLE risk_flag_member (              -- 위험 조건 ↔ 요구사항·값 (값 불일치는 2개 이상)
  risk_id         INT NOT NULL REFERENCES risk_flag(risk_id),
  requirement_id  INT NOT NULL REFERENCES requirement(requirement_id),
  value_id        INT REFERENCES req_value(value_id),
  PRIMARY KEY (risk_id, requirement_id)
);

CREATE TABLE judgment (                      -- 적합성 판정 + 여유 (FR-07). 묶음 A·B만
  judgment_id     SERIAL PRIMARY KEY,
  run_id          INT NOT NULL REFERENCES review_run(run_id),
  requirement_id  INT NOT NULL REFERENCES requirement(requirement_id),
  value_id        INT REFERENCES req_value(value_id),
  product_code    VARCHAR(40) REFERENCES product_master(product_code),  -- 비교 제품 행
  product_value_raw VARCHAR(100),
  result          VARCHAR(25) NOT NULL CHECK (result IN
                   ('COMPLY','DEVIATION_CANDIDATE','QUERY_CANDIDATE','NEEDS_REVIEW','WARRANTY_TO_FILL')),
  reason_code     VARCHAR(30),                      -- NO_PRODUCT_VALUE, UNIT_DIFF, BOUNDARY, DELEGATED ...
  compare_rule_id INT REFERENCES compare_rule(compare_rule_id),
  margin_value    NUMERIC(18,6),                    -- 여유 (차이 또는 배수)
  margin_kind     VARCHAR(10) CHECK (margin_kind IN ('DIFF','RATIO','TIME_RATIO')),
  margin_direction VARCHAR(12) NOT NULL DEFAULT 'NOT_CALC'
                   CHECK (margin_direction IN ('STRENGTH','NOT_STRENGTH','NOT_CALC')),
  is_current      BOOLEAN NOT NULL DEFAULT TRUE,    -- "다른 제품으로 바꿔 보기" 하면 이전 판정은 FALSE
  CHECK (margin_direction = 'NOT_CALC' OR result = 'COMPLY')
);

CREATE TABLE engineering_check (             -- 공학 규칙 검산 (FR-12, 규칙 하나)
  check_id        SERIAL PRIMARY KEY,
  run_id          INT NOT NULL REFERENCES review_run(run_id),
  rule_code       VARCHAR(10) NOT NULL DEFAULT 'B1',
  ik_value_id     INT NOT NULL REFERENCES req_value(value_id),   -- 단시간 전류
  peak_value_id   INT NOT NULL REFERENCES req_value(value_id),   -- 최대 순간(투입) 전류
  freq_value_id   INT REFERENCES req_value(value_id),            -- 주파수
  expected_ka     NUMERIC(8,2),
  result          VARCHAR(12) NOT NULL CHECK (result IN ('PASS','VIOLATION','NEEDS_REVIEW'))
);

CREATE TABLE warranty_candidate (            -- 보증값 후보 (FR-08)
  candidate_id    SERIAL PRIMARY KEY,
  run_id          INT NOT NULL REFERENCES review_run(run_id),
  judgment_id     INT NOT NULL REFERENCES judgment(judgment_id),   -- result = WARRANTY_TO_FILL
  candidate_value VARCHAR(200),                     -- 비면 "확인 필요"
  source_kind     VARCHAR(10) CHECK (source_kind IN ('PM','FIXED')),
  product_code    VARCHAR(40) REFERENCES product_master(product_code),
  pm_column       VARCHAR(40),
  fixed_key       VARCHAR(40) REFERENCES company_fixed_value(fixed_key),
  status          VARCHAR(12) NOT NULL CHECK (status IN ('CANDIDATE','EMPTY_REVIEW','CONFIRMED')),
  CHECK (candidate_value IS NOT NULL OR status = 'EMPTY_REVIEW')
);

CREATE TABLE loss_calc (                     -- 손실 환산 (FR-13)
  loss_calc_id    SERIAL PRIMARY KEY,
  run_id          INT NOT NULL REFERENCES review_run(run_id),
  clause_requirement_id INT NOT NULL REFERENCES requirement(requirement_id),  -- 손실 환산 조항
  product_code    VARCHAR(40) REFERENCES product_master(product_code),
  price_noload    NUMERIC(12,2) NOT NULL,           -- $/kW (RFP 원문)
  price_load      NUMERIC(12,2) NOT NULL,
  price_aux       NUMERIC(12,2) NOT NULL,
  loss_noload_kw  NUMERIC(10,2),
  loss_load_kw    NUMERIC(10,2),
  loss_aux_kw     NUMERIC(10,2),
  total_usd       NUMERIC(16,2),                    -- 손실값이 하나라도 없으면 NULL (확인 필요)
  is_assumed      BOOLEAN NOT NULL                  -- 팀 가정 표시
);

CREATE TABLE output_item (                   -- 일탈·질의 목록 항목 (FR-09)
  item_id         SERIAL PRIMARY KEY,
  run_id          INT NOT NULL REFERENCES review_run(run_id),
  list_kind       VARCHAR(10) NOT NULL CHECK (list_kind IN ('DEVIATION','QUERY')),
  text_draft      TEXT NOT NULL,                    -- 숫자는 자리표시자를 코드가 채운 결과
  basis_requirement_id INT REFERENCES requirement(requirement_id),  -- 근거 조항 (서면 문의 조항 등)
  number_check    VARCHAR(10) NOT NULL CHECK (number_check IN ('OK','MISMATCH')),
  status          VARCHAR(12) NOT NULL CHECK (status IN ('DRAFT','CONFIRMED','REMOVED'))
);

CREATE TABLE output_item_source (            -- 목록 항목의 출처 (판정 / 위험 조건 / 검산)
  item_id         INT NOT NULL REFERENCES output_item(item_id),
  source_seq      SMALLINT NOT NULL,
  judgment_id     INT REFERENCES judgment(judgment_id),
  risk_id         INT REFERENCES risk_flag(risk_id),
  check_id        INT REFERENCES engineering_check(check_id),
  PRIMARY KEY (item_id, source_seq),
  CHECK (num_nonnulls(judgment_id, risk_id, check_id) = 1)
);

CREATE TABLE output_item_link (              -- 질의 ↔ 일탈 연결 (사례 15)
  item_id         INT NOT NULL REFERENCES output_item(item_id),
  linked_item_id  INT NOT NULL REFERENCES output_item(item_id),
  PRIMARY KEY (item_id, linked_item_id),
  CHECK (item_id <> linked_item_id)
);

CREATE TABLE submission_check (              -- 제출 전 누락 점검 (FR-09)
  check_id        SERIAL PRIMARY KEY,
  run_id          INT NOT NULL REFERENCES review_run(run_id),
  deviation_candidates INT NOT NULL,
  deviation_listed     INT NOT NULL,
  missing_judgment_ids INT[] NOT NULL DEFAULT '{}',
  open_queries         INT NOT NULL,
  checked_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE proposal_point (                -- 기술 제안 포인트 (FR-14)
  point_id        SERIAL PRIMARY KEY,
  run_id          INT NOT NULL REFERENCES review_run(run_id),
  point_kind      VARCHAR(10) NOT NULL CHECK (point_kind IN ('MARGIN','LOSS','FIELD')),
  requirement_id  INT NOT NULL REFERENCES requirement(requirement_id),     -- 근거 1: 요구 원문
  product_code    VARCHAR(40) NOT NULL REFERENCES product_master(product_code),  -- 근거 2: 제품 행
  judgment_id     INT REFERENCES judgment(judgment_id),     -- MARGIN
  loss_calc_id    INT REFERENCES loss_calc(loss_calc_id),   -- LOSS
  fault_link_id   INT REFERENCES fault_link(fault_link_id), -- FIELD
  text_draft      TEXT,
  number_check    VARCHAR(10) CHECK (number_check IN ('OK','MISMATCH')),
  is_assumed      BOOLEAN NOT NULL DEFAULT FALSE,
  status          VARCHAR(10) NOT NULL CHECK (status IN ('CANDIDATE','ADOPTED','DISCARDED','EDITED')),
  CHECK ( (point_kind='MARGIN' AND judgment_id  IS NOT NULL)
       OR (point_kind='LOSS'   AND loss_calc_id IS NOT NULL)
       OR (point_kind='FIELD'  AND fault_link_id IS NOT NULL) )
);

-- ---------------------------------------------------------------------
-- ⑥ 확인·승인·전달 (FR-10, FR-11)
-- ---------------------------------------------------------------------
CREATE TABLE review_log (                    -- 수정 이력 (모든 결과 표 공통)
  log_id          BIGSERIAL PRIMARY KEY,
  run_id          INT NOT NULL REFERENCES review_run(run_id),
  target_table    VARCHAR(40) NOT NULL,             -- judgment, output_item, warranty_candidate, proposal_point, risk_flag
  target_id       INT NOT NULL,
  action          VARCHAR(12) NOT NULL CHECK (action IN ('CONFIRM','EDIT','REJECT','ADOPT','DISCARD')),
  before_value    JSONB,
  after_value     JSONB,
  reason          TEXT,
  actor_id        INT NOT NULL REFERENCES app_user(user_id),
  acted_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE approval_rule (                 -- 승인 기준 (AR-01,02,03,06,07,08)
  ar_code         VARCHAR(6) PRIMARY KEY,
  description     TEXT NOT NULL,
  threshold       NUMERIC(6,3)                      -- AR-03: 0.20
);

CREATE TABLE approval (
  approval_id     SERIAL PRIMARY KEY,
  run_id          INT NOT NULL REFERENCES review_run(run_id),
  approver_id     INT REFERENCES app_user(user_id),
  decision        VARCHAR(10) CHECK (decision IN ('APPROVED','REJECTED')),  -- 대기 중이면 NULL
  comment         TEXT,
  requested_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  decided_at      TIMESTAMPTZ
);

CREATE TABLE approval_reason (               -- 승인 요청에 걸린 기준
  approval_id     INT NOT NULL REFERENCES approval(approval_id),
  ar_code         VARCHAR(6) NOT NULL REFERENCES approval_rule(ar_code),
  detail          TEXT,
  PRIMARY KEY (approval_id, ar_code)
);

CREATE TABLE assignment (                    -- 유형별 담당자 전달 (FR-11)
  assignment_id   SERIAL PRIMARY KEY,
  run_id          INT NOT NULL REFERENCES review_run(run_id),
  assignee_role   VARCHAR(20) NOT NULL CHECK (assignee_role IN ('ENGINEER','COST','QUALITY','SALES')),
  assignee_id     INT REFERENCES app_user(user_id),
  requirement_id  INT REFERENCES requirement(requirement_id),
  point_id        INT REFERENCES proposal_point(point_id),     -- 채택된 제안 포인트만 (AR-08)
  repeat_count    INT NOT NULL DEFAULT 1,           -- "같은 조건 ○개 장비에 반복"
  status          VARCHAR(10) NOT NULL CHECK (status IN ('TODO','DOING','DONE')),
  sent_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (num_nonnulls(requirement_id, point_id) = 1)
);
