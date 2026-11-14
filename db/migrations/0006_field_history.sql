-- FR-15 현장 이력 연결(add-field-history)에 필요한 칸

-- 고장 사전: 의심 사례를 가리는 데 쓰는 기준 (RMA 필요 여부, 보통 처리 시간)
ALTER TABLE fault_catalog ADD COLUMN needs_rma BOOLEAN;
ALTER TABLE fault_catalog ADD COLUMN typical_hours NUMERIC(8,2);

-- 해결 사례: 의심 판단에 쓰는 원본 값과 의심 이유 (NULL이면 정상 사례)
ALTER TABLE resolution_case ADD COLUMN product_code VARCHAR(40);       -- 프로젝트 1 제품 코드 (우리 제품표와 다름)
ALTER TABLE resolution_case ADD COLUMN rma_no VARCHAR(30);
ALTER TABLE resolution_case ADD COLUMN resolution_result VARCHAR(40);
ALTER TABLE resolution_case ADD COLUMN resolve_hours NUMERIC(8,2);
ALTER TABLE resolution_case ADD COLUMN suspect_reason TEXT;

-- 연결표: 제품군은 고장 사전의 제품군이다. 제품표를 바꿔도(seed-products --replace) 연결표가
-- 지워지지 않도록 product_family 참조를 뗀다. 적용 설비는 요구사항의 설비 종류 코드 목록이다.
ALTER TABLE fault_link DROP CONSTRAINT fault_link_product_family_fkey;
ALTER TABLE fault_link ADD COLUMN equipment_kinds TEXT[] NOT NULL DEFAULT '{}';
ALTER TABLE fault_link ADD COLUMN source_note TEXT;                    -- 근거 원문 위치 (연결표를 만들 때 본 곳)

-- 제안 포인트: 현장 이력 후보는 제품 행 대신 연결표 줄이 근거다
ALTER TABLE proposal_point ALTER COLUMN product_code DROP NOT NULL;
ALTER TABLE proposal_point ADD CONSTRAINT proposal_point_product_check
  CHECK (point_kind = 'FIELD' OR product_code IS NOT NULL);
-- 연결표에서 뺀 줄의 현장 이력 후보는 함께 지운다
ALTER TABLE proposal_point DROP CONSTRAINT proposal_point_fault_link_id_fkey;
ALTER TABLE proposal_point ADD CONSTRAINT proposal_point_fault_link_id_fkey
  FOREIGN KEY (fault_link_id) REFERENCES fault_link(fault_link_id) ON DELETE CASCADE;
