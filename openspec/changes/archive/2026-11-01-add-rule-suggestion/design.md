# Design

## 표 (마이그레이션 0023)

`rule_suggestion(suggestion_id, dictionary 'risk-expressions', expression, note, run_id, requirement_id, status PENDING|ACCEPTED|DECLINED, suggested_by, suggested_at, decided_by, decided_at, decision_reason, edit_id → rule_edit)`.

## 제안 (`pipeline/rule_suggestion.py`)

- 표현: 앞뒤 공백 없앰, 2~100자.
- 근거: 이 검토 문서의 요구사항(`req_kind` 상관없이 문장·표 칸) 중 공백·대소문자를 무시하고 표현을 포함하는 첫 줄(요구사항 번호가 가장 작은 것). 없으면 400 "이 검토 문서에서 찾지 못했습니다".
- 이미 켜진 사전 줄과 같은 표현(대소문자 무시)이면 409. 확인 대기 중인 같은 표현이면 409.
- 제안할 수 있는 단계: 처리 중·실패가 아닌 검토. 누구나(역할 제한 없음) — 판정 규칙 화면이 확인한다.

## 반영·반려

- 엔지니어·승인자만(`rule_edit` 규칙과 같음).
- 반영: `rule_edit.add('risk-expressions', {expression, language, risk_kind, context_rule}, 사유)` 뒤 `ACCEPTED`, `edit_id` 저장. 한 트랜잭션.
- 반려: 사유 필수, `DECLINED`.
- 이미 결정한 제안은 409.

## API

- `GET /api/runs/{id}/rule-suggestions`, `POST /api/runs/{id}/rule-suggestions {expression, note, actor_id}`
- `GET /api/rule-suggestions?status=`, `POST /api/rule-suggestions/{id}/accept {value, reason, actor_id}`, `POST /api/rule-suggestions/{id}/decline {reason, actor_id}`

## 화면

- 위험 조건 탭 `.rk` 영역: 예시 띠·예시 줄 지움. 입력 칸 + 메모 + "제안 추가", 이 검토의 제안 줄(표현, 찾은 곳, 상태 칩).
- 판정 규칙 `.rkp` 영역: 예시 띠 지움. 최근 제안(확인 대기 먼저) 줄마다 날짜·표현·찾은 곳·제안한 사람·상태, 확인 대기 줄에 [반영]·[반려]. [반영]은 기존 규칙 창(RuleDialog)에 표현을 채워 연다.

## 대안

- 위험 조건 탭에서 바로 사전에 넣기: 사전 판이 바뀌어 모든 문서를 다시 처리하게 되므로 규칙 담당 확인을 둔다(목업 문구 "규칙 담당 확인 대기"와 같음).
