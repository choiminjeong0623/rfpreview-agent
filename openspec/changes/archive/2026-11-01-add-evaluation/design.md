# Design

## 1. 표 (마이그레이션 0022)

- `answer_key(key_id, key_name UNIQUE, key_kind 'TYPE', made_by 'CLAUDE_DRAFT'|'HUMAN', created_at)`
- `answer_key_row(key_id, row_no, text_raw, context, expected, ambiguous, human_checked, note)`
- `eval_score(score_id, run_ids INT[], key_id NULL, metrics JSONB, note, code_version, scored_by, scored_at)`
- `review_log`·`judgment`는 바꾸지 않는다.

## 2. 정답지 CSV

Claude 초안 열 이름을 그대로 받는다: `번호, text, context, Claude초안, 애매함(Y), 이유, 사람 확인(...)`. 영어 열 이름(`row_no, text, context, expected, ambiguous, note, human`)도 받는다.
정답 = 사람 확인 칸이 있으면 그 값, 없으면 초안 값. 사람 확인 칸이 있는 줄은 `human_checked`. 같은 이름으로 다시 넣으면 줄을 바꾼다.
`made_by`는 명령 옵션 `--human`이 없으면 CLAUDE_DRAFT.

## 3. 지표 계산 (`pipeline/evaluation.py`)

- 대상 판정: 고른 검토의 지금 판정(`is_current`), 반려(해당 없음) 제외.
- 시스템 판정: 확정(CONFIRMED)이면 지금 판정. 수정(EDITED)이면 그 판정의 첫 수정 이력 `before_value.result`. 이력이 없으면(문서 추가로 이어받은 줄) 모름 → K5·K6 분모에서 뺀다.
- K13 맞추기: 글자 정규화(공백 하나, 앞뒤 공백, 대소문자) 같은 요구사항(고른 검토 문서의 REQUIREMENT). 여럿이면 하나라도 정답이면 맞음이 아니라, **요구사항 번호가 가장 작은 것**으로 정한다(CR-11). 주 유형 태그가 없으면 NONE. 찾지 못한 줄은 "못 찾음"으로 센다(분모에서 뺌). 애매한 줄은 맞음·틀림과 별도로 보인다.
- 처리 시간: `finished_at - started_at` 평균(끝난 검토만).
- 지표마다 `{code, name, measure, unit, value, num, den, target, better, basis, note}`. 비율은 소수 1자리 %.
- 목표: 기획서 2-2 가안(K4 100 %, K5 80 %, K6 80 %, K11 0, K12 0, K13 70 %, 처리 시간 15분 이하).

## 4. 화면

- 목업 Eval 구조 그대로(채점 결과·정답지·개선 기록 탭). 지난 값 = 바로 앞 채점 기록.
- 정답지 탭: 검토 표(넣기 체크, 검토, 확정한 사람, 마지막 확정, 사람이 본 판정 줄)와 유형 정답지 고르기(줄 수, 사람 확인 n/전체, "Claude 초안·사람 확인 전" 꼬리표).
- "지금 채점하기": 넣은 검토·고른 정답지·메모(무엇을 고쳤나)로 채점 실행 → 결과 탭.

## 대안

- 정답지를 화면에서 올리기: 파일 올리기 화면이 하나 더 필요하다. 명령으로 충분하다.

## 위험

- K5·K6는 엔지니어가 확정한 줄만 정답으로 본다. 확정한 줄이 적으면 점수가 흔들린다 → 분자·분모를 함께 보인다.
- Claude 초안 정답지는 사람 정답이 아니다 → 화면과 발표에 "사람 확인 전"을 항상 붙인다.
