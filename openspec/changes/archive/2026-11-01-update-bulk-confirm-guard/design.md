# 설계

- `review.bulk_confirm`: 현재 판정·단계 검사(지금과 같음) 뒤 `_bulk_risks(conn, run_id, ids)`로 줄마다 뺄 이유를 구한다. 이유가 여럿이면 CHECK → MISMATCH → NO_VALUE 순으로 하나.
  - CHECK: `engineering_check.result <> 'PASS'`이고 최대 순간 전류 값 또는 단시간 전류 값의 요구사항이 그 판정의 요구사항.
  - MISMATCH: `output_item_source.judgment_id`로 이어진 목록 항목(지운 것 빼고) 중 `number_check = 'MISMATCH'`.
  - NO_VALUE: 판정 결과가 확인 필요·작성 필요이고 `product_value_raw`가 비었음.
- 응답 `BulkResult`에 `skipped: [{judgment_id, reason}]`.
- 모두 빠지면 `ReviewError(400, "한꺼번에 확정할 수 있는 줄이 없습니다 …")`. 이력·확정 없음.
- 대안: 경고만 하고 그대로 확정 — 사람이 보지 않고 넘기는 문제가 남아 뺐다.
