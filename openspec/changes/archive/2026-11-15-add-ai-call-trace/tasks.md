# Tasks

## 1. 기록

- [x] 1.1 `llm/trace.py`: 세션(contextvar)·기록·버린 이유·저장·원문 지우기, 해시·묶음 줄 수
- [x] 1.2 `llm/client.py`: `call_with_retry(role=)` 시도마다 기록, 결과 종류, 모델별 `last_tokens`
- [x] 1.3 `llm/tasks.py`: 역할 넘기기, 위험 설명·초안 버린 이유
- [x] 1.4 `llm/parallel.py`·문서 병렬 처리: 작업마다 context 이어받기
- [x] 1.5 마이그레이션 `0043_ai_call.sql`, 설정 `RFP_TRACE_RAW` 세 곳

## 2. 세션 주인

- [x] 2.1 분석(`execute_run`·`_set_step`), 검토 도우미, 협조 요청 질문, 프롬프트 평가

## 3. 조회

- [x] 3.1 `pipeline/ai_calls.py`: 목록·요약·다른 답·OTLP JSON
- [x] 3.2 API `GET /runs/{id}/ai-calls`, `/ai-calls/otel`, 상태 점검 `trace_raw`, 스키마, `npm run gen:api`
- [x] 3.3 실행 기록 화면 "AI 호출"

## 4. 테스트

- [x] 4.1 review-run Scenario 8개
