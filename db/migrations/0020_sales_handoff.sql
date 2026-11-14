-- 영업 인계 (add-submission-package, FR-11 확장): 데이터시트·인계 패키지를 영업 주소로 넘긴 기록.
-- 내려받기만 하면 기록하지 않는다. 다시 넘기면 새 줄. 화면은 마지막 줄을 보인다.
CREATE TABLE sales_handoff (
  handoff_id  SERIAL PRIMARY KEY,
  run_id      INT NOT NULL REFERENCES review_run(run_id),
  kind        VARCHAR(10) NOT NULL CHECK (kind IN ('DATASHEET','PACKAGE')),
  table_id    INT REFERENCES doc_table(table_id),            -- 데이터시트일 때만
  file_names  TEXT[] NOT NULL,                               -- 붙인 파일 (패키지는 zip 안 파일)
  mail_to     TEXT,                                          -- 주소 없음이면 NULL
  mail_error  TEXT,                                          -- 주소 없음·발송 실패
  sent_by     INT NOT NULL REFERENCES app_user(user_id),
  sent_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX sales_handoff_run ON sales_handoff (run_id, kind, table_id);
