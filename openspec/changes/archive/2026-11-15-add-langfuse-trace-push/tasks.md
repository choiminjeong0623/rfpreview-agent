## 1. 백엔드

- [x] 1.1 마이그레이션 0046: `review_run.langfuse_sent_at`·`langfuse_url`·`langfuse_error`
- [x] 1.2 `langfuse_ops.send_run`: 기록 켬·호출 있을 때 보내고 결과를 검토에 남김, `run_queue.run` 작업 끝에서 부름(실패해도 작업 결과 그대로)
- [x] 1.3 `ai_calls.summary`·`AiCalls.langfuse`, `npm run gen:api`, 설정 설명 고침

## 2. 화면

- [x] 2.1 실행 기록 상세 AI 호출: Langfuse로 보낸 시각·링크, 보내지 못한 이유(중립색)

## 3. 문서·검사

- [x] 3.1 테스트 `tests/test_langfuse_trace_push.py`(가짜 Langfuse)
- [x] 3.2 ADR-011·README·SCR-25 문서
- [x] 3.3 검사, archive, AGENTS.md 표, `npm run trace`
