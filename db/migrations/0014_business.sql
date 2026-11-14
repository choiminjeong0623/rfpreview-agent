-- 사업 현황 (add-project-status): 입찰 한 건(사업)에 Lot·설비 범위별 검토 여러 개를 묶는다.
-- `project` 표(0001)와 뜻이 다르다. `project` = FR-06 값 불일치 비교 범위(document_catalog 기준표),
-- `business` = 사람이 만드는 사업. 두 표는 잇지 않고, 사업 연결은 판정·후보 계산에 쓰지 않는다.
-- 진행 상태는 저장하지 않고 연결된 검토에서 계산한다.
CREATE TABLE business (
  business_id     SERIAL PRIMARY KEY,
  business_name   VARCHAR(200) NOT NULL,
  customer_name   VARCHAR(200),
  country         VARCHAR(60),
  tender_no       VARCHAR(80),                       -- 고객 입찰 번호
  order_mode      VARCHAR(200),                      -- 발주 방식 (예: Lot 3개로 분할 발주)
  due_date        DATE,                              -- 제출 마감일
  sales_id        INT REFERENCES app_user(user_id),  -- 영업 담당
  created_by      INT NOT NULL REFERENCES app_user(user_id),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  submitted_at    TIMESTAMPTZ,                       -- 사람이 표시한 제출 완료 (CR-08)
  submitted_by    INT REFERENCES app_user(user_id)
);

-- 사업 정보 고침 이력. review_log는 run_id가 필수라 따로 둔다
CREATE TABLE business_log (
  log_id          BIGSERIAL PRIMARY KEY,
  business_id     INT NOT NULL REFERENCES business(business_id),
  field           VARCHAR(40) NOT NULL,              -- 칸 이름, 제출 완료는 submitted
  before_value    JSONB,
  after_value     JSONB,
  actor_id        INT NOT NULL REFERENCES app_user(user_id),
  acted_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE review_run ADD COLUMN business_id INT REFERENCES business(business_id);
CREATE INDEX ix_review_run_business ON review_run(business_id);

-- 기존 검토 묶기: 사업명 글자(앞뒤 공백만 지움)가 같은 검토를 사업 하나로. 정보는 가장 먼저 시작한 검토 값
WITH firsts AS (
  SELECT DISTINCT ON (trim(project_name)) trim(project_name) AS name, customer_name, country,
         due_date, started_by, started_at
  FROM review_run
  WHERE trim(COALESCE(project_name, '')) <> ''
  ORDER BY trim(project_name), started_at, run_id
)
INSERT INTO business (business_name, customer_name, country, due_date, created_by, created_at)
SELECT name, customer_name, country, due_date, started_by, started_at FROM firsts ORDER BY started_at;

UPDATE review_run r SET business_id = b.business_id
FROM business b WHERE trim(r.project_name) = b.business_name;
