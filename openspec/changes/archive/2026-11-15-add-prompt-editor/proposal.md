# Proposal

## Why

Langfuse 연동(add-langfuse-prompts) 뒤 프롬프트 글은 Langfuse 화면에서 고치고, 평가·운영 반영은 `rfp-db eval-prompts --promote` 명령으로 했다. 사용자가 프롬프트 고치기를 RFP 화면 안(프롬프트 관리)에서 하고 싶다고 했다(11-15). Langfuse 화면을 iframe으로 끼우면 로그인·권한·검사(CR-14)를 우리가 지킬 수 없으므로, 같은 Langfuse 공개 API를 우리 화면에서 부른다.

관련: FR-18·NFR-13(add-prompt-eval), ADR-011(add-langfuse-prompts), SCR-26 프롬프트 관리.

## What Changes

- 프롬프트 관리 화면의 줄을 누르면 오른쪽 패널: 판 기록, 프롬프트 글(운영·staging 판), 자리표시자·문서 본문 규칙 검사 표시.
- Langfuse가 연결되어 있으면 엔지니어·승인자가 글을 고쳐 [staging에 저장] → Langfuse에 staging 표시를 단 새 버전. 운영 판은 그대로. 검사(자리표시자·데이터 규칙)에 걸리거나 staging과 같은 글이면 저장하지 않는다.
- [평가 돌리기]: 공개 평가셋에서 그 역할 문항만 staging 판으로 3번 반복해 기준선과 비교, 결과를 평가 기록에 저장하고 패널에 지표·회귀 여부를 보인다(웹 서버 안 백그라운드 스레드, 한 번에 하나).
- [운영으로 올리기]: 승인자만, 평가가 끝났고 회귀·기준선 없음이 아니며 평가한 판이 아직 staging일 때만 production 표시를 그 판으로 옮긴다.
- Langfuse가 꺼져 있거나 닿지 못하면 코드 틀만 보이고 고치기는 잠긴다. AI를 끈 설정이면 평가가 잠긴다.
- API: `GET /api/prompts/{role}`, `POST /api/prompts/{role}/drafts`, `POST /api/prompts/{role}/evaluations`, `GET /api/prompts/{role}/evaluations/latest`, `POST /api/prompts/{role}/promote`. 마이그레이션 없음.

## Non-Goals

- Langfuse 화면을 iframe으로 넣기.
- 관리자 역할 만들기(지금 역할 표에 없음, 승인자를 쓴다).
- 평가 작업을 실행 대기열(`run_job`)에 넣기. 평가 작업 상태는 웹 서버 메모리에만 있다(서버를 다시 띄우면 사라지고 평가 기록은 DB에 남는다).
