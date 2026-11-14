-- 4단계 확인·승인(add-review-approval)에 필요한 칸

-- 판정: 엔지니어 확인 상태 (후보 → 확정 / 수정 / 반려). 수정 내용은 review_log에 남는다
ALTER TABLE judgment ADD COLUMN review_status VARCHAR(10) NOT NULL DEFAULT 'CANDIDATE'
  CHECK (review_status IN ('CANDIDATE','CONFIRMED','EDITED','REJECTED'));

-- 보증값: 엔지니어가 넣은 값과 반려
ALTER TABLE warranty_candidate DROP CONSTRAINT warranty_candidate_status_check;
ALTER TABLE warranty_candidate ADD CONSTRAINT warranty_candidate_status_check
  CHECK (status IN ('CANDIDATE','EMPTY_REVIEW','CONFIRMED','REJECTED'));
ALTER TABLE warranty_candidate DROP CONSTRAINT warranty_candidate_source_kind_check;
ALTER TABLE warranty_candidate ADD CONSTRAINT warranty_candidate_source_kind_check
  CHECK (source_kind IN ('PM','FIXED','ENGINEER'));
ALTER TABLE warranty_candidate DROP CONSTRAINT warranty_candidate_check;
ALTER TABLE warranty_candidate ADD CONSTRAINT warranty_candidate_check
  CHECK (candidate_value IS NOT NULL OR status IN ('EMPTY_REVIEW','REJECTED'));

-- 목록 항목·제안 포인트: 엔지니어가 고쳐 쓴 문장
ALTER TABLE output_item DROP CONSTRAINT output_item_drafted_by_check;
ALTER TABLE output_item ADD CONSTRAINT output_item_drafted_by_check
  CHECK (drafted_by IN ('CODE','AI','ENGINEER'));
ALTER TABLE proposal_point DROP CONSTRAINT proposal_point_drafted_by_check;
ALTER TABLE proposal_point ADD CONSTRAINT proposal_point_drafted_by_check
  CHECK (drafted_by IN ('CODE','AI','ENGINEER'));

-- 수정 이력: 손실 환산 고치기도 남긴다 (대상 표 이름은 그대로 text)
CREATE INDEX ix_review_log_run ON review_log (run_id, acted_at);

-- 로그인(범위 밖) 전까지 쓰는 기본 승인자
INSERT INTO app_user (user_name, role) VALUES ('기본 승인자', 'APPROVER');
