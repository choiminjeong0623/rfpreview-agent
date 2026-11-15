# Design

## 결정

1. **작업이 끝날 때 한 번.** 실행 대기열 작업(`run_queue.run`)이 `run_to_end`를 마친 뒤 보낸다. 단계마다 보내면 Langfuse 지연이 분석 시간에 붙는다. 웹 서버 안(inline)·처리기(worker) 방식 모두 같은 자리를 지난다.
2. **검토 전체를 다시 보낸다.** `ai_calls.otel`은 검토의 모든 호출을 보내고 trace id(검토 + 실행 토큰)·span id(호출 번호)가 정해진 식이라, 문서 추가·단계부터 다시로 작업이 여러 번이어도 Langfuse에서 늘지 않는다(덮어씀). 보낸 내용은 내려받기·명령과 같다.
3. **같은 설정 `RFP_LANGFUSE_RECORD`.** 평가 실험(add-langfuse-experiments)과 함께 "Langfuse에 기록 남김"을 켠다. 기본 off라 운영자가 모르게 밖으로 나가지 않고, `/api/health` `langfuse_record`로 켜짐이 보인다(ADR-011에서 버린 "저절로 보내기"의 걱정을 기본 off·상태 점검 표시로 푼다).
4. **결과는 검토 줄에.** `review_run.langfuse_sent_at`·`langfuse_url`(이번 작업 trace 화면 `<호스트>/project/<프로젝트>/traces/<trace>`)·`langfuse_error`. 성공하면 오류를 비우고, 실패하면 시각은 그대로 두고 이유만 바꾼다. 실행 기록 상세 AI 호출 응답(`AiCalls.langfuse`)에 실어 화면이 보인다.
5. **실패는 중립색.** Langfuse가 꺼졌거나 닿지 않는 것은 사용자 잘못이 아니고 검토 결과와 상관없다(CR-12의 원인 알림).

## 버린 대안

- 별도 주기 작업으로 모아 보내기: 처리기·스케줄러가 하나 더 생긴다. 작업 끝 한 번이면 충분하다.
- RFP 화면 대시보드: 실행 기록 "AI 사용량"과 Langfuse 기본 대시보드가 같은 것을 보인다.

## 위험

- 실제 self-host Langfuse로 끝까지 돌려 보지 못했다. 가짜 서버로 시험했다. trace 화면 주소 모양 [확인 필요].
- Langfuse 요청 시간 제한(`RFP_LANGFUSE_TIMEOUT_S`, 기본 5초)만큼 작업 끝이 늦어질 수 있다. 검토 단계는 이미 담당자 확인이라 사용자는 기다리지 않는다.
