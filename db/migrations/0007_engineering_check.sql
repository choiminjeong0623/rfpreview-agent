-- FR-12 공학 규칙 검산(add-engineering-check)에 필요한 칸

-- 쓴 배수(2.5 / 2.6)와 확인 필요 사유 (NO_FREQUENCY, MULTI_FREQUENCY, MULTI_IK, UNIT_DIFF)
ALTER TABLE engineering_check ADD COLUMN factor NUMERIC(3,1);
ALTER TABLE engineering_check ADD COLUMN reason_code VARCHAR(30);
