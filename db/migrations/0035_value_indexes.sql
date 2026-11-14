-- 판정 값 읽기(judge.VALUES_SQL)·비교 제품 칸(/equipment)이 큰 검토에서 느림: 요구사항마다 값을
-- 전부 훑었다 (파일 1: 값 4,929개 × 80,438행). 결과는 그대로, 찾는 길만 더한다
CREATE INDEX IF NOT EXISTS ix_req_value_requirement ON req_value (requirement_id);
CREATE INDEX IF NOT EXISTS ix_table_row_parent ON table_row (parent_row_id);
