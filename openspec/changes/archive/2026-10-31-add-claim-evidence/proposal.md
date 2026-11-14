# Proposal

## Why

AI가 쓰는 위험 조건 설명(FR-06)은 지금 숫자만 검사한다(CR-07). 설명 문장이 원문의 어느 곳을 근거로 했는지는 남지 않는다.
그래서 사람이 그 설명을 원문과 대조할 수 없고, 근거 없는 설명이 숫자만 맞으면 그대로 저장된다.
박경빈 님 브랜치 `KB/feat/환각-방지`에서 시작한 일을 정리해 넣는다(2026-10-31 minjeong 결정).

관련: FR-06, CR-01·02·07·12, `evidence-integrity`, `risk-detection`.

## What Changes

- 위험 조건 설명을 부를 때 후보 요구사항의 원문 위치마다 근거 조각 ID(`E-문서-위치`)를 붙여 준다.
- AI는 설명 문장(claim)마다 근거 조각 ID, 그 조각에서 그대로 옮긴 인용, 관계(그대로·계산·추론)를 낸다.
- 코드가 대조한다: 주지 않은 ID, 고른 조각에 없는 인용, 사실·근거에 없는 숫자가 하나라도 있으면 설명 전체를 버린다.
- 통과한 문장은 인용·근거 위치와 함께 저장한다(새 표 `claim_evidence`, `claim_evidence_source`, 마이그레이션 0016).
- AI가 정해진 횟수 안에 답하지 못하면 다른 AI 단계와 같이 실패로 알린다(CR-12). 숨기지 않는다.

## Impact

- 코드: `llm/evidence.py`(새), `llm/tasks.py` `explain_risk`, `pipeline/run.py` 위험 조건 저장
- DB: `db/migrations/0016_claim_evidence.sql` (0015는 `update-role-handoff-mail`이 쓴다)
- 화면·API 변경 없음. 저장된 근거를 화면에 보이는 일은 나중 change.
