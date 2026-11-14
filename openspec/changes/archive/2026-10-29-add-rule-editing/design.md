# Design

## 결정 (2026-10-29 minjeong 결정: "DB가 원본, 수정 이력 남김")

- **원본은 DB, CSV는 시작값.** 화면 고침은 DB에 바로 쓰고 `rule_edit`(마이그레이션 0013)에 동작 기록을 남긴다.
  `rule_edit(edit_id, dictionary, row_key JSONB, action ADD|EDIT|DELETE, before_value JSONB, after_value JSONB, reason, actor_id, edited_at, discarded_at)`.
- **줄 키(자연 키)** — 다시 적재해도 같은 줄을 찾게 서버 id 대신 쓴다.
  비교 방향: (table_name, item_no, item_key) · 위험 표현: expression · 항목 이름: item_key(같은 뜻 표현은 표준 항목 줄의 칸) · 문서 종류: priority.
- **다시 적재**: `seed_rules`가 CSV를 넣은 뒤 버리지 않은 `rule_edit`을 edit_id 순서로 다시 적용한다. 적용 못 하면 건너뛰고 보고에 적는다.
  `rfp-db seed-rules --reset-edits`는 남은 고침에 `discarded_at`을 찍고 CSV만 남긴다.
- **사전 판**: `dict_version = sha(CSV 파일들)[:12]`에 버리지 않은 고침이 있으면 `+e<마지막 edit_id>`를 붙인다. 같은 CSV와 같은 고침이면 같은 판(CR-11).
  `make_context`가 DB를 읽어 판을 만든다.
- **검사는 적재와 같은 코드표**: 방향·강점·위험 종류·문서 종류 코드(DB CHECK와 같은 값), 정규식(문서 종류). 화면은 CSV의 한글 기호("≥") 대신 코드로 보내므로 적재의 기호 변환은 쓰지 않고, 문서 종류 코드표(`DOC_KINDS`)는 적재와 같이 쓴다.
- **삭제는 끄기**: 지난 검토 결과(판정의 compare_rule_id, 위험 후보의 expr_id, 값의 item_key)가 사전 줄을 가리키므로 지우지 않고 `active = false`로 끈다(마이그레이션 0013에서 compare_rule·risk_expression·item_key에 칸 추가).
  꺼진 줄은 화면 목록과 새 검토에서 빠지고, 지난 결과의 이름 표시는 그대로다. 같은 키로 다시 추가하면 다시 켠다. 문서 종류 규칙은 가리키는 곳이 없어 실제로 지운다.
  적재도 CSV에서 사라진 비교 방향·위험 표현 줄을 지우지 않고 끈다.
- **표준 항목 삭제 막기**: 켜진 비교 방향 줄이나 제품표 연결(item_pm_mapping)이 가리키면 409와 쓰는 곳 수.
- **권한**: 요청의 actor_id 역할이 ENGINEER·APPROVER일 때만(로그인은 범위 밖이라 다른 화면과 같은 방식). [제안]
- **API**: `POST /api/rules/{dictionary}`, `PUT /api/rules/{dictionary}/{id}`, `DELETE /api/rules/{dictionary}/{id}` (본문에 사유·actor_id), `GET /api/rules/edits?dictionary=`. dictionary = compare, risk-expressions, items, doc-kinds.
- **값 모양**: 고치기 API의 `value`는 DB 칸 이름·코드 그대로(예: 방향 `GE`, 위험 종류 `OPEN_SCOPE`). 같은 뜻 표현은 표준 항목 줄의 `aliases` 목록.
  표준 항목 키는 바꿀 수 없다(다른 표가 가리킴). 비교 방향 목록에 이 줄에 적은 강점 방향(`own_strength_direction`)을 더해, 비어 있으면 고치기 창도 "기본값 따름"으로 둔다.
  표준 항목을 지우면 그 같은 뜻 표현도 지운다(다른 항목이 쓸 수 있게, 이력에는 남음).
- **화면**: 제목 줄 "규칙 추가"(지금 탭), 펼친 줄에 수정·삭제, 결재 상신 창과 같은 모양의 입력 창. "마지막 수정"은 마지막 고침(사람·시각), 수정 이력은 그 줄의 `rule_edit`.

## 대안

- 고침을 CSV에 다시 쓰기 → 서버가 저장소 파일을 고쳐 git 충돌이 쉽다.
- 수정 요청 → 승인 → 반영 → 만들 것이 두 배. 나중에 `rule_edit`에 상태 칸을 더해 붙일 수 있다.

## 위험

- 잘못 고치면 다음 검토 전부에 영향 → 사유 필수, 이력, 고침 버리기.
- 고침 다시 적용이 CSV 변경과 부딪침 → 건너뛰고 알림.
