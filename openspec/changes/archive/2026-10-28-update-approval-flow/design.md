# Design

## Context

`review.finish_review`는 승인 기준을 계산해 걸리면 `APPROVAL`, 안 걸리면 바로 `APPROVED`로 두고 `approval` 행을 만든다
(안 걸리면 `decision='APPROVED'`, 의견 "승인 기준에 해당 없음"). `decide`는 승인자 역할만 확인하고 가장 최근 `approval` 행을 갱신한다.
`approval.approver_id`는 결정할 때 채운다. `reopen`은 반려된 실행만 되돌린다. 단계 변경은 `review_log`(`target_table='review_run'`)에 남는다.

## Decisions

### 1. 항상 승인 대기
- `finish_review`(API 이름은 그대로 `finish-review`, 화면 문구는 "결재 상신")는 걸린 기준과 관계없이 `APPROVAL`로 둔다.
  `approval_reason`에는 지금처럼 걸린 기준만 넣는다(없으면 0행).
- 명세서 FR-10 [결정]을 바꾸는 부분이라 2026-10-28 minjeong이 "항상 결재 받기"로 정했다. 명세서 문서 개정 때 함께 반영한다.
- 대안: 기준에 안 걸리면 지금처럼 바로 승인하되 결재자·의견만 받기 → 목업과 다르고, 기준이 없을 때 결재자를 받는 의미가 없다.

### 2. 스키마
- 마이그레이션 다음 번호: `approval`에 `requested_by INT REFERENCES app_user(user_id)`, `request_comment TEXT`,
  `withdrawn_at TIMESTAMPTZ` 추가. `decision` CHECK를 `('APPROVED','REJECTED','WITHDRAWN')`로 바꾼다.
- `approver_id`는 상신할 때 지정 결재자로 채운다. 기존 행(이미 결정된 것)은 그대로 둔다.
- 지금 열려 있는 승인 대기 행(`decision IS NULL`)은 `approver_id`가 비어 있으므로, 마이그레이션에서 기본 승인자(`role='APPROVER'` 중 가장 작은 id)로 채운다.

### 3. API
- `POST /finish-review` 본문 `Submit`: `actor_id`, `approver_id`(필수), `comment`(필수, 공백만이면 400).
  결재자 역할이 `APPROVER`가 아니면 400, 없는 사용자 404.
- `POST /approval`(결정): 가장 최근의 결정 전 행의 `approver_id`와 `actor_id`가 다르면 403 "지정된 결재자만 결정할 수 있습니다".
- `POST /withdraw` 새로 추가, 본문 `Actor`: `APPROVAL` 단계에서만(아니면 409, 지금 `require_stage` 오류와 같은 방식).
  엔지니어 역할만. 행은 `decision='WITHDRAWN'`, `withdrawn_at=now()`, 실행은 `ENGINEER_REVIEW`. 이력 `action='EDIT'`, 사유 "상신 취소".
- `GET /approval` 응답의 `approval`에 `requested_by`(이름), `request_comment`, `approver_id`를 더한다. 취소된 행은 "최근 상신"으로 보이지 않게 결정 전·결정 난 행만 고른다.
- `GET /tasks`의 승인자 카드: `APPROVAL` 단계이고 최근 결정 전 행의 `approver_id = user_id`인 실행만.

### 4. 반려 뒤 다시 상신
- `reopen` 뒤 다시 상신하면 새 `approval` 행을 만든다(지금과 같음). 결재자는 다시 고른다(화면은 직전 결재자를 미리 골라 둠).

### 5. 화면
- "확인 마침" 버튼을 "결재 상신"으로 바꾸고 창을 연다: 검토 요약(일탈·질의·확인 필요·작성 필요 수, 손실 환산), 상신 전 확인(지금 걸리는 기준 미리 보기 = 기존 `preview`), 결재자 고르기(승인자 사용자), 상신 의견(필수).
- 승인 대기 화면: 상신한 사람·시각·결재자·상신 의견. 엔지니어로 보면 "상신 취소" 버튼, 지정 결재자로 보면 승인·반려, 다른 승인자는 읽기만.

## Risks / Trade-offs

- **BREAKING**: `finish-review`에 결재자·의견이 없으면 400이 된다. CLI나 테스트에서 이 API를 부르는 곳을 함께 고친다.
- 기준에 안 걸린 실행도 사람이 결재해야 해서 시연·테스트 단계가 하나 늘어난다. 대신 "사람이 확인하지 않은 결과는 나가지 않는다"(CR-08)가 더 분명해진다.
- 결재자 1명만 지원한다. 여러 단계 결재선은 Non-Goal.


## 결정 기록 (구현 중)

- [결정] 승인 화면 응답에 `review_ratio`(확인 필요 건수·전체·기준)를 더했다. 상신 창과 결재 대기 화면의 "확인 필요 비율" 칸을 AR-03과 같은 계산으로 보이기 위해서다(CR-01: 화면이 따로 계산하지 않음).
- [결정] 결재 대기 화면(SCR-12)은 주소를 따로 두지 않고, 승인 대기인 검토를 `#/reviews/{id}`로 열면 보인다. 목업도 결재 대기 검토는 Wait 화면으로 연다.
- [결정] 결재 상신은 엔지니어 역할만 한다(403). 상신 취소도 엔지니어 역할만 한다. 로그인이 없어 기안자 본인인지는 따지지 않는다.
- e2e는 판정이 나오는 합성 데이터시트(`frontend/e2e/fixtures/synthetic_judgment.docx`)를 쓴다. 판정하려면 로컬 DB의 문서 목록에 묶음 A로 넣어야 하며, 없으면 건너뛴다.
