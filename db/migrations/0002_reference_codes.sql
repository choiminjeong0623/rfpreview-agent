-- 고정 코드표와 schema_v1 보완 (명세서 v1 2-1, 2-2, 3장 승인 기준)

-- 비교 방향 사전에 "원문 기호 따름"(< / ≤ 를 요구값 기호대로) 줄이 있어 SOURCE를 더한다.
ALTER TABLE item_key DROP CONSTRAINT item_key_default_direction_check;
ALTER TABLE item_key ADD CONSTRAINT item_key_default_direction_check
  CHECK (default_direction IN ('EQ','GE','LE','LT','IN','FILL','TEXT','SOURCE'));
ALTER TABLE compare_rule DROP CONSTRAINT compare_rule_direction_check;
ALTER TABLE compare_rule ADD CONSTRAINT compare_rule_direction_check
  CHECK (direction IN ('EQ','GE','LE','LT','IN','FILL','TEXT','AI','SOURCE'));

INSERT INTO requirement_type (type_code, type_name, default_role) VALUES
  ('TECH_PERF',     '기술 성능',      'ENGINEER'),
  ('RISK',          '위험 조건',      'ENGINEER'),
  ('STANDARD_CERT', '적용 규격·인증', 'ENGINEER'),
  ('COST',          '비용 영향',      'COST'),
  ('TEST',          '시험',           'QUALITY'),
  ('MAKER_QUAL',    '제조사 자격',    'SALES'),
  ('SITE_ENV',      '설치 환경',      'ENGINEER');

INSERT INTO approval_rule (ar_code, description, threshold) VALUES
  ('AR-01', '일탈 후보가 1건 이상', NULL),
  ('AR-02', '포괄 조항이 탐지됨', NULL),
  ('AR-03', '"확인 필요" 비율이 기준값 초과 (보증값 후보를 채운 칸은 빼고 계산)', 0.200),
  ('AR-06', '해결되지 않은 값 불일치·질의가 남아 있음', NULL),
  ('AR-07', '일탈 후보 중 일탈 목록에 들어가지 않은 것이 있음', NULL),
  ('AR-08', '기술 제안 포인트는 채택 표시한 것만 전달', NULL);

-- 칸 이름 사전: 명세서 FR-02에 적힌 것만. 나머지는 사전 작성 후 추가.
INSERT INTO column_role_dict (header_text, column_role) VALUES
  ('Employer''s Requirement', 'REQUIRED'),
  ('Warranted Data',          'WARRANTED'),
  ('C/D/E',                   'SUPPLIER_MARK');
