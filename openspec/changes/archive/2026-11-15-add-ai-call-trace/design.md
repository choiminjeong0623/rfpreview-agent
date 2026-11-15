# Design: AI 호출 기록 (add-ai-call-trace)

## 1. 기록하는 자리 (`llm/trace.py`, `llm/client.py`)

- AI 문장 요청은 모두 `call_with_retry`를 지난다. 여기에 `role`(역할 8개 중 하나)을 받아 **시도마다** 한 건을 남긴다. 그래서 호출 기록 수 = 실행 기록의 AI 호출 수(재시도 포함).
- 토큰: `GeminiLLM`·`LocalLLM`이 `generate_json`에서 쓴 토큰을 스레드마다 `last_tokens`에도 둔다(동시 호출이라 전체 Usage 차이로는 한 호출을 못 가름). 대역 모델은 0.
- 결과: `OK` / `FORMAT_ERROR`(JSON 아님·검사 실패) / `CONFIG_ERROR` / `TIMEOUT`(TimeoutError·이름에 timeout) / `CONNECTION_ERROR`(그 밖의 재시도 오류).
- 버린 이유: 호출은 성공했지만 코드 검사(위험 설명 근거 대조 `UNKNOWN_EVIDENCE` 등, 초안 자리표시자)로 버리면 `trace.drop(reason)`이 이 스레드의 마지막 기록에 적는다.
- 해시: `sha256(프롬프트 + 답 형식)` 앞 16자, `sha256(답 JSON, sort_keys)` 앞 16자. 원문은 `RFP_TRACE_RAW=on`일 때만 기록에 붙는다.
- 묶음 줄 수: 프롬프트의 번호 줄 수(`^\d+\. `).

## 2. 기록 세션 (contextvar)

- `trace.session(run_id, token, feature)`가 contextvar에 세션(목록 + 잠금)을 둔다. 세션이 없으면 기록하지 않는다(CLI·단위 시험이 개발 DB에 쓰지 않게).
- 처리 단계는 `trace.set_step(step)`(run `_set_step`이 부름).
- 동시 호출(`llm/parallel.run_ordered`, 문서 병렬 처리)은 작업마다 `contextvars.copy_context().run`으로 같은 세션을 이어받는다.
- 저장은 세션 주인이 자기 연결로 한다(`trace.flush(conn)`): 분석은 단계가 바뀔 때마다와 끝·실패 때(`execute_run`), 도우미·협조 질문은 요청 끝, 평가는 실행 끝. 저장이 실패해도 경고 로그만 남기고 처리는 계속한다.

## 3. 표 (마이그레이션 0043)

- `ai_call(call_id BIGSERIAL, run_id NULL, run_token, feature, step, role, model, prompt_version, attempt, started_at, ended_at, duration_ms, input_tokens, output_tokens, thinking_tokens, result, dropped_reason, input_hash, output_hash, batch_lines)`. 색인 `(run_id, call_id)`, `(input_hash)`.
- `ai_call_raw(call_id PK → ai_call ON DELETE CASCADE, prompt, answer, created_at)`. `RFP_TRACE_RAW=on`일 때만 쓴다. `trace.purge(conn)`가 7일(`RAW_KEEP_DAYS`) 지난 원문만 지운다(분석 시작 때와 상태 점검 때).

## 4. 조회·내보내기 (`pipeline/ai_calls.py`, API)

- `GET /api/runs/{id}/ai-calls`: 호출 목록(시각 순), 요약(호출 수, 결과별 수, 단계별 걸린 시간 합, 다른 답 수). 다른 답 = 이 검토 호출 중, 입력 해시가 같은 다른 호출(다른 검토 포함)과 출력 해시가 다른 성공 호출 수.
- `GET /api/runs/{id}/ai-calls/otel`: OTLP JSON(`resourceSpans`). 호출마다 span 하나, 속성 `gen_ai.operation.name=chat`, `gen_ai.request.model`, `gen_ai.usage.input_tokens`·`output_tokens`, `rfp.role`, `rfp.prompt_version`, `rfp.step`, `rfp.result`, 해시. trace id는 검토 번호·실행 토큰에서 만든다(같은 검토는 같은 trace).
- `/api/health`: `trace_raw`(원문 저장 켜짐)와 켜졌으면 안내 문장.

## 5. 화면 (SCR-25 실행 기록)

- 펼친 줄 "AI 호출": 단계·역할 칩 거르기, 기본은 시각 순, "느린 순" 단추. 줄마다 단계·역할·모델·판·걸린 시간·토큰·결과(성공은 중립색)·버린 이유·묶음 줄 수. 위에 단계별 걸린 시간 막대(AI 호출 시간 합). 기록이 없으면 "호출 기록 없음".
- "OpenTelemetry로 내보내기" 링크(JSON 내려받기).

## 대안

- **LangSmith·OpenTelemetry SDK를 바로 붙임**: 고객 문서 처리 환경에서 외부 전송을 기본으로 둘 수 없고 의존성이 는다. 이름 규칙만 맞춘 JSON을 내보내 필요하면 사람이 넣는다.
- **호출마다 바로 DB에 씀**: 분석 연결은 시험·CLI에서 개발 DB와 다를 수 있어, 세션 주인의 연결로 모아 쓴다.

## 위험

- 프로세스가 단계 중간에 죽으면 그 단계의 기록은 잃는다(단계마다 저장).
- 해시 앞 16자는 충돌 가능성이 아주 낮지만 0은 아니다.
