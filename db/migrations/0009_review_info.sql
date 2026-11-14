-- 검토 정보 (add-review-info): 사람이 넣는 값이라 원문 위치가 없고 판정에 쓰지 않는다. 모두 비어 있어도 된다.
ALTER TABLE review_run ADD COLUMN project_name  VARCHAR(200);                       -- 사업명 (목업 "사업명")
ALTER TABLE review_run ADD COLUMN review_name   VARCHAR(200);                       -- 검토명 = 설비 범위
ALTER TABLE review_run ADD COLUMN customer_name VARCHAR(200);
ALTER TABLE review_run ADD COLUMN country       VARCHAR(60);
ALTER TABLE review_run ADD COLUMN due_date      DATE;                               -- 제출 마감일
ALTER TABLE review_run ADD COLUMN engineer_id   INT REFERENCES app_user(user_id);   -- 담당 엔지니어
