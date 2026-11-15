# Proposal

## Why

프롬프트 글은 코드(`llm/tasks.py`)에서만 고칠 수 있어, 프롬프트를 조금 바꿔 보려 해도 코드 배포가 필요하다. 어느 판이 운영에 쓰이는지, 평가를 통과한 판인지도 배포 기록과 따로 논다. ADR-010(add-prompt-view)에서 편집·배포를 self-host Langfuse로 넘기는 설계를 적었고, 사용자가 그 연동을 구현하자고 했다(11-15).

관련: FR-18·NFR-13(add-prompt-eval), FR-21(add-ai-call-trace), ADR-010, SCR-26 프롬프트 관리.

## What Changes

- 역할 8개의 프롬프트를 코드 틀(자리표시자 `{{이름}}`)로 바꾼다. 모델에 보내는 글은 지금과 한 글자도 다르지 않다(해시 그대로).
- `RFP_LANGFUSE=on`이면 self-host Langfuse에서 역할마다 `rfp-<역할>` 프롬프트의 `RFP_LANGFUSE_LABEL`(기본 production) 판을 가져와 쓴다. 판 설정의 코드 판이 다르거나, 자리표시자가 코드 틀과 다르거나, 문서 본문은 데이터라는 규칙(CR-14)이 빠졌거나, Langfuse에 닿지 못하면 그 역할은 코드 판으로 돌아간다. 기본은 off(지금과 같음).
- 실행 기록·재사용 열쇠·AI 호출 기록에 실제로 쓴 판(`t2+lf4`)을 남긴다. 한 실행 안에서는 시작할 때 고른 판을 계속 쓴다.
- `rfp-db langfuse-push-prompts [--label staging]`: 코드 틀을 Langfuse 새 버전으로 올림.
- `rfp-db eval-prompts --promote`: staging 판으로 평가해 기준선보다 나빠지지 않았을 때만 그 판에 production 표시를 옮김.
- `rfp-db langfuse-push-traces --run N`: 검토 실행의 AI 호출 기록(OTLP JSON, 원문 없이 해시만)을 Langfuse로 보내고 Langfuse 판으로 부른 호출은 그 프롬프트 버전과 잇는다.
- `/api/health`에 프롬프트를 가져오는 곳, 프롬프트 관리 화면에 역할마다 가져온 곳(Langfuse 버전·코드로 돌아간 이유).
- 마이그레이션 없음.

## Non-Goals

- RFP 화면 안에서 프롬프트 글 고치기(글은 Langfuse 화면에서 고친다).
- Langfuse 서버를 이 저장소의 docker compose에 넣기(공식 compose로 따로 띄운다, 설치 안내).
- 자동 호출 기록 보내기(사람이 명령으로 보낸다).
