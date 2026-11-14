-- FR-11 유형별 담당자 전달(add-role-assignment)에 필요한 칸

-- 할 일 키: 다시 만들어도 같은 할 일이면 진행 상태를 이어 쓴다
--   요구사항 "R|역할|같은 조건 문장", 제안 포인트 "P|역할|종류|요구 id|근거"
ALTER TABLE assignment ADD COLUMN task_key TEXT;
-- 같은 조건이 여러 장비에 반복되면 한 건으로 묶고 묶인 요구사항을 모두 남긴다 (대표는 requirement_id)
ALTER TABLE assignment ADD COLUMN requirement_ids INT[] NOT NULL DEFAULT '{}';
ALTER TABLE assignment ADD COLUMN type_code VARCHAR(20) REFERENCES requirement_type(type_code);
ALTER TABLE assignment ADD COLUMN updated_at TIMESTAMPTZ;
CREATE UNIQUE INDEX ux_assignment_task ON assignment(run_id, task_key);

-- 제안 포인트를 다시 만들면(손실값 고치기 등) 포인트가 지워져도 전달 기록은 남겨 둔다.
-- 바로 뒤 담당자 전달 단계가 할 일 키로 진행 상태를 이어 쓰고 새 포인트를 가리키게 다시 만든다.
ALTER TABLE assignment DROP CONSTRAINT assignment_check;
ALTER TABLE assignment ADD CONSTRAINT assignment_check
  CHECK (num_nonnulls(requirement_id, point_id) <= 1);
ALTER TABLE assignment DROP CONSTRAINT assignment_point_id_fkey;
ALTER TABLE assignment ADD CONSTRAINT assignment_point_id_fkey
  FOREIGN KEY (point_id) REFERENCES proposal_point(point_id) ON DELETE SET NULL;

-- 담당자 기본 사용자 (로그인 없이 화면에서 고른다)
INSERT INTO app_user (user_name, role) VALUES
  ('기본 견적 담당', 'COST'), ('기본 품질 담당', 'QUALITY'), ('기본 영업 담당', 'SALES');
