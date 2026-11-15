# Proposal

## Why

분석 AI 호출 기록은 `rfp-db langfuse-push-traces --run N`으로 사람이 검토마다 보내야 Langfuse에 간다. 그래서 단계·모델·프롬프트 판별 비용·지연을 Langfuse 기본 대시보드로 보려면 검토마다 명령을 돌려야 했다. 사용자가 Langfuse LLMOps 계획(11-15) 가운데 3번(분석 뒤 호출 기록 자동 전송, 대시보드는 Langfuse 기본 화면)을 1번(add-langfuse-experiments) 다음에 하기로 했다.

관련: FR-21(add-ai-call-trace), ADR-011(add-langfuse-prompts), add-langfuse-experiments, SCR-25 실행 기록.

## What Changes

- `RFP_LANGFUSE_RECORD=on`(add-langfuse-experiments의 같은 설정, 기본 off)이면 검토 실행 작업(등록·다시 시도·문서 추가·단계부터 다시)이 끝날 때 그 검토의 AI 호출 기록을 Langfuse로 보낸다. 내용은 `langfuse-push-traces`·OpenTelemetry 내려받기와 같다(원문 없이 해시, Langfuse 판 호출은 프롬프트 버전 연결).
- 보낸 시각과 이번 작업 trace의 Langfuse 주소, 또는 보내지 못한 이유를 검토에 남긴다. 실행 기록 상세 "AI 호출"에 "Langfuse로 보냄 · 시각 · Langfuse에서 보기" 또는 중립색 "Langfuse로 보내지 못함: 이유".
- 보내지 못해도 검토 단계·결과는 바뀌지 않는다. AI 호출이 없는 작업(AI 끔 등)은 보내지 않는다.
- 비용·지연 대시보드는 Langfuse 기본 화면을 쓴다(RFP 화면 대시보드는 만들지 않음).
- 마이그레이션 0046: `review_run.langfuse_sent_at`·`langfuse_url`·`langfuse_error`.

## Non-Goals

- RFP 화면 안 비용·지연 대시보드(실행 기록 "AI 사용량"이 이미 있음).
- 분석 단계마다 보내기, 분석 밖 호출(검토 도우미 등) 보내기.
- 원문 보내기(해시만, 지금과 같음).
