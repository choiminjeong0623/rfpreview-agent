-- 문서 읽기 점검(update-review-screens 묶음 7, SCR-08-2): 시스템이 제대로 읽지 못한 곳을 사람이 직접 확인한 기록

-- 문서 안 그림 위치. 그림 속 글자는 읽지 않는다 (OCR 범위 밖)
CREATE TABLE doc_figure (
  figure_id       SERIAL PRIMARY KEY,
  document_id     INT NOT NULL REFERENCES document(document_id),
  section_id      INT REFERENCES section(section_id),
  line_no         INT NOT NULL,                     -- 그림 단락의 줄 번호
  caption         TEXT                              -- "Fig. 6-2 Single Line Diagram" (앞뒤 단락에서 찾음)
);

-- 점검 줄 확인. check_key는 점검 줄의 종류와 원천 id로 만든다 (T:표, F:그림, D:문서, U:단위, P:위치)
CREATE TABLE read_check (
  read_check_id   SERIAL PRIMARY KEY,
  run_id          INT NOT NULL REFERENCES review_run(run_id),
  check_key       VARCHAR(60) NOT NULL,
  label           TEXT NOT NULL,                    -- 이력에 쓰는 이름 "<위치> (<무엇>)"
  checked_by      INT REFERENCES app_user(user_id),
  checked_at      TIMESTAMPTZ,                      -- 되돌리면 비운다
  UNIQUE (run_id, check_key)
);

-- 되돌리기도 이력에 남긴다
ALTER TABLE review_log DROP CONSTRAINT review_log_action_check;
ALTER TABLE review_log ADD CONSTRAINT review_log_action_check
  CHECK (action IN ('CONFIRM','EDIT','REJECT','ADOPT','DISCARD','UNDO'));
