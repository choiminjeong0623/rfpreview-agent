-- 검토 실행 대기열 (add-run-queue, FR-20·NFR-11·NFR-12)
-- 등록·다시 시도·문서 추가·단계부터 다시는 작업만 넣고, 처리기가 들어온 순서대로 꺼낸다.
CREATE TABLE run_job (
  job_id        SERIAL PRIMARY KEY,
  run_id        INT NOT NULL REFERENCES review_run(run_id),
  kind          VARCHAR(10) NOT NULL CHECK (kind IN ('START', 'RETRY', 'ADD_DOCS', 'REWIND')),
  status        VARCHAR(8) NOT NULL DEFAULT 'QUEUED'
                  CHECK (status IN ('QUEUED', 'RUNNING', 'DONE', 'FAILED', 'DROPPED')),
  payload       JSONB NOT NULL,                 -- {paths, choices, rewind}
  token         UUID NOT NULL,                  -- 이 작업의 실행 토큰
  worker        TEXT,
  attempts      INT NOT NULL DEFAULT 0,         -- 살아 있음이 끊겨 다시 넣은 횟수
  heartbeat_at  TIMESTAMPTZ,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at    TIMESTAMPTZ,
  finished_at   TIMESTAMPTZ,
  error         TEXT
);
CREATE INDEX run_job_queue ON run_job (status, job_id);
CREATE INDEX run_job_run ON run_job (run_id, job_id);

-- 지금 이 검토를 돌릴 자격이 있는 실행 토큰 (가장 최근 넣은 작업). 다르면 실행은 결과를 쓰지 않는다
ALTER TABLE review_run ADD COLUMN run_token UUID;

-- 처리기 살아 있음 (상태 점검의 처리기 수)
CREATE TABLE run_worker (
  worker_id     TEXT PRIMARY KEY,
  started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  heartbeat_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 중복 등록 방지: 같은 요청 키가 10분 안에 다시 오면 처음 만든 검토
CREATE TABLE run_request (
  request_key   VARCHAR(80) PRIMARY KEY,
  run_id        INT REFERENCES review_run(run_id),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 등록 미리 보기 결과 (파일 내용 해시). 등록 검사가 파일을 다시 읽지 않게
CREATE TABLE preview_cache (
  content_hash  CHAR(64) PRIMARY KEY,
  result        JSONB NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
