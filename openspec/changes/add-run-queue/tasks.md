# Tasks

## 1. 대기열

- [ ] 1.1 마이그레이션 `0042_run_queue.sql`: `run_job`, `run_worker`, `run_request`, `preview_cache`, `review_run.run_token`
- [ ] 1.2 `pipeline/run_queue.py`: enqueue·claim·run·reclaim·drain·serve·queue_position, 살아 있음 스레드
- [ ] 1.3 `rfp-worker` 명령(pyproject), docker compose `worker` 서비스
- [ ] 1.4 설정 `RFP_RUN_MODE`·`RFP_RUN_WORKERS`·`RFP_UPLOAD_MAX_MB`·`RFP_REQUEST_MAX_MB` 세 곳

## 2. 소유권

- [ ] 2.1 `run.py`: `RunContext.token`, `check_cancel` 토큰 검사, `RunSuperseded`, 끝·실패 기록은 자기 토큰일 때만
- [ ] 2.2 `run_control.py`: 대기 중 취소, 멈춤 판단을 살아 있음으로

## 3. API

- [ ] 3.1 등록·다시 시도·문서 추가·단계부터 다시 → enqueue (+ inline이면 drain)
- [ ] 3.2 등록 검사 가볍게(`preview_cache`, OCR 없는 읽기), 요청 키, 업로드 상한
- [ ] 3.3 `RunSummary`·`RunListItem` `queue_position`·`heartbeat_at`, `/api/health` 처리기·대기 작업, `npm run gen:api`

## 4. 화면

- [ ] 4.1 검토 목록·머리글 진행 "대기 중 n번째"
- [ ] 4.2 멈춤 판단 살아 있음 기준
- [ ] 4.3 등록 요청 키

## 5. 테스트

- [ ] 5.1 review-run Scenario 10개
- [ ] 5.2 기존 등록·다시 시도·문서 추가·단계부터 다시 테스트 통과
