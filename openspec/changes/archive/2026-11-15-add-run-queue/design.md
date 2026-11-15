# Design: 검토 실행 대기열 (add-run-queue)

## 1. 표 (마이그레이션 0042)

- `run_job(job_id, run_id, kind START|RETRY|ADD_DOCS|REWIND, status QUEUED|RUNNING|DONE|FAILED|DROPPED, payload JSONB {paths, choices, rewind}, token UUID, worker TEXT, attempts INT, heartbeat_at, created_at, started_at, finished_at, error)`. 꺼내기 색인 `(status, job_id)`.
- `review_run.run_token UUID` — 지금 이 검토를 돌릴 자격이 있는 토큰(가장 최근 넣은 작업의 토큰).
- `run_worker(worker_id, started_at, heartbeat_at)` — 상태 점검의 살아 있는 처리기 수.
- `run_request(request_key PK, run_id, created_at)` — 중복 등록 방지.
- `preview_cache(content_hash PK, result JSONB, created_at)` — 미리 보기 결과(분류·묶음·판독·읽지 못한 쪽 이유). 등록 검사가 다시 읽지 않게.

단계(`stage`)에 새 값을 넣지 않는다. 대기 중은 `PROCESSING` 안의 상태(`graph_state.step = 'queued'`)이고, 응답 `queue_position`으로 보인다. 단계 값을 쓰는 화면·흐름 표(STOPS·NEXT)를 바꾸지 않으려는 것.

## 2. 작업 넣기·꺼내기 (`pipeline/run_queue.py`)

- `enqueue(conn, run_id, kind, payload)`: 새 토큰을 만들어 `review_run.run_token`에 쓰고(옛 실행은 이때 소유권을 잃음) 같은 검토의 QUEUED 작업은 DROPPED, 새 작업 QUEUED. 커밋.
- `claim(conn, worker_id, limit)`: 트랜잭션 advisory lock 안에서 RUNNING 수가 limit 미만이면 가장 오래된 QUEUED를 `FOR UPDATE SKIP LOCKED`로 꺼내 RUNNING. 토큰이 검토의 지금 토큰과 다르면 DROPPED로 건너뜀.
- `run(job, worker_id)`: 살아 있음 스레드(30초)를 켜고 `service.run_to_end(..., token=job.token)`. 끝나면 DONE / FAILED / 소유권을 잃었으면 DROPPED.
- `reclaim(conn)`: RUNNING인데 살아 있음이 3분(`OWNERSHIP_SECONDS`) 넘게 없는 작업 → `attempts < 2`면 새 토큰으로 다시 QUEUED(attempts+1, 흐름은 저장된 checkpoint에서 이어감), 아니면 FAILED + 검토 "처리 실패 — 처리기가 멈춤"(그 토큰일 때만).
- `drain(limit)`: reclaim → claim이 None일 때까지 꺼내 돌린다. inline 방식의 API 백그라운드 작업이 쓴다.
- `serve()`(`rfp-worker`): 처리기 등록·살아 있음, `RFP_RUN_WORKERS`개 스레드가 2초마다 claim, 30초마다 reclaim.
- `queue_position(conn, run_id)`: 그 검토의 QUEUED 작업보다 먼저 들어온 QUEUED 수 + 1.

## 3. 실행 소유권 (`pipeline/run.py`)

- `RunContext.token`. `check_cancel(conn, run_id, token)`은 취소 요청과 함께 `run_token`이 자기 토큰인지 본다. 다르면 `RunSuperseded`.
- `execute_run`은 `RunSuperseded`면 아무것도 쓰지 않고 `"SUPERSEDED"`를 돌려준다. 끝 단계·실패 기록은 `WHERE run_token IS NOT DISTINCT FROM %s`로 자기 토큰일 때만.
- 토큰 없이 부르는 CLI·테스트(`token=None`)는 지금처럼 검사하지 않는다.

## 4. 등록 검사 (`pipeline/preview.py`)

- `preview()`가 결과를 `preview_cache`에 넣는다(파일 해시 기준).
- `judge_target_problem(..., light=True)`: 캐시가 있으면 그 값으로, 없으면 docx는 OCR 없이 읽고(`docx_reader.read_blocks(path, use_ocr=False)`), PDF는 첫 쪽 글자 층만(`pdf_reader.first_page_blocks`) 읽어 분류한다. 첫 쪽에 글자가 없는 PDF는 판단하지 않는다(분석에 맡김). 읽지 못해 거절하는 것(add-unread-pages)은 캐시가 있을 때만.

## 5. 설정 (config.py, .env.example, docker-compose.yml)

- `RFP_RUN_MODE` inline(기본)·worker. docker compose는 worker로 두고 `worker` 서비스(`rfp-worker`)를 더한다.
- `RFP_RUN_WORKERS`(2), `RFP_UPLOAD_MAX_MB`(100), `RFP_REQUEST_MAX_MB`(300).
- 상수: 살아 있음 30초, 소유권 3분, 다시 넣기 2번, 요청 키 10분.

## 6. 취소·멈춤

- 대기 중 검토 취소: 작업 DROPPED, 검토는 바로 FAILED(취소 문구).
- 처리 중 취소의 "멈춤" 판단(`request_cancel`): 작업이 있으면 살아 있음 3분, 없으면 지금처럼 진행 10분.
- 화면: `RunSummary`·`RunListItem`에 `queue_position`, `heartbeat_at`. 멈춤 안내는 살아 있음이 있으면 3분 기준.

## 대안

- **Redis·Celery**: 기획서에서 다음 단계로 미룬 것. DB 하나로 충분하고 서버를 늘리지 않는다.
- **단계에 QUEUED 추가**: 화면·흐름 표·상태 칩을 모두 고쳐야 한다. PROCESSING 안의 하위 상태로 둔다.
- **처리기만 두고 inline 없음**: 개발·시험·e2e가 모두 처리기를 따로 띄워야 한다. inline도 같은 대기열 규칙을 지킨다.

## 위험

- inline 방식은 웹 서버 프로세스 안이라 (다)는 worker 방식에서만 풀린다. 운영(docker compose)은 worker.
- 다시 넣은 실행이 흐름 상태(checkpoint)를 이어받으므로 옛 실행이 남긴 단계 결과를 다시 쓸 수 있다. 단계마다 지우고 다시 만드는 지금 규칙(CR-11)으로 결과는 같다.
