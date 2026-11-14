-- 3단계 판정과 결과물(add-judgment-and-outputs)에 필요한 칸과 표

-- 제품표: 정격 용량 (변압기 설계 카드 고르기). 단위는 원문 그대로 (CR-10)
ALTER TABLE product_master ADD COLUMN rated_capacity NUMERIC(12,3);
ALTER TABLE product_master ADD COLUMN rated_capacity_unit VARCHAR(10);

-- 판정: 설비 묶음, 사람이 읽는 사유, 팀 가정 표시 (CR-06), 제품값 단위
ALTER TABLE judgment ADD COLUMN equipment_group VARCHAR(160);       -- 비교 제품을 고른 묶음 (표·구분 또는 문서·설비)
ALTER TABLE judgment ADD COLUMN reason_text TEXT;
ALTER TABLE judgment ADD COLUMN product_value_unit VARCHAR(40);
ALTER TABLE judgment ADD COLUMN product_selected_by VARCHAR(10) CHECK (product_selected_by IN ('AUTO','ENGINEER'));
ALTER TABLE judgment ADD COLUMN is_assumed BOOLEAN NOT NULL DEFAULT FALSE;
CREATE INDEX ix_judgment_run ON judgment (run_id, is_current);

-- 엔지니어가 고른 비교 제품 ("다른 제품으로 바꿔 보기")
CREATE TABLE run_product_choice (
  run_id          INT NOT NULL REFERENCES review_run(run_id),
  equipment_group VARCHAR(160) NOT NULL,
  product_code    VARCHAR(40) NOT NULL REFERENCES product_master(product_code),
  chosen_by       INT REFERENCES app_user(user_id),
  chosen_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (run_id, equipment_group)
);

-- 보증값 후보: 단위와 비운 사유
ALTER TABLE warranty_candidate ADD COLUMN candidate_unit VARCHAR(40);
ALTER TABLE warranty_candidate ADD COLUMN reason_code VARCHAR(30);   -- NOT_MAPPED, NO_PRODUCT_VALUE, PRODUCT_AMBIGUOUS
ALTER TABLE warranty_candidate ADD COLUMN is_assumed BOOLEAN NOT NULL DEFAULT FALSE;

-- 손실 환산: 단가 단위, 계산 상태, 계산식
ALTER TABLE loss_calc ADD COLUMN price_unit VARCHAR(20);
ALTER TABLE loss_calc ADD COLUMN status VARCHAR(12) NOT NULL DEFAULT 'CALCULATED'
  CHECK (status IN ('CALCULATED','NEEDS_REVIEW'));
ALTER TABLE loss_calc ADD COLUMN reason_code VARCHAR(30);            -- NO_LOSS_VALUE, PRICE_UNIT, NO_PRODUCT
ALTER TABLE loss_calc ADD COLUMN formula TEXT;
ALTER TABLE loss_calc ADD COLUMN price_requirement_ids INT[] NOT NULL DEFAULT '{}';  -- 단가 행 (원문 위치)

-- 목록 항목: 발주처 양식 이름, 묶음 키, 숫자 검사 내용, 팀 가정
ALTER TABLE output_item ADD COLUMN list_name VARCHAR(200);
ALTER TABLE output_item ADD COLUMN group_key TEXT;
ALTER TABLE output_item ADD COLUMN number_detail TEXT;                -- 근거와 다른 숫자
ALTER TABLE output_item ADD COLUMN drafted_by VARCHAR(10) NOT NULL DEFAULT 'CODE'
  CHECK (drafted_by IN ('CODE','AI'));
ALTER TABLE output_item ADD COLUMN is_assumed BOOLEAN NOT NULL DEFAULT FALSE;

-- 제안 포인트: 근거 값과 숫자 검사 내용
ALTER TABLE proposal_point ADD COLUMN basis TEXT;                     -- 요구값·제품값·여유 (코드가 씀)
ALTER TABLE proposal_point ADD COLUMN number_detail TEXT;
ALTER TABLE proposal_point ADD COLUMN drafted_by VARCHAR(10) NOT NULL DEFAULT 'CODE'
  CHECK (drafted_by IN ('CODE','AI'));

-- 누락 점검: 걸린 승인 기준 (AR-07)
ALTER TABLE submission_check ADD COLUMN ar_codes VARCHAR(6)[] NOT NULL DEFAULT '{}';
