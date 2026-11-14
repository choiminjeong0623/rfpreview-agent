# 설계: add-type-examples

## 결정

- **고치기 API**: `POST /api/runs/{run_id}/requirements/{requirement_id}/type` {type_code, reason, actor_id}. 주 유형 태그를 지우고 HUMAN 주 태그를 넣는다(같은 유형의 보조 태그가 있으면 지움). 미분류(NONE)를 고르면 주 태그를 지운다. 이력 target "requirement", action EDIT(이력 action 제약을 바꾸지 않으려고 EDIT_TYPE 대신). 그 뒤 `build_assignments`(협조 요청은 이미 보낸 기록을 task_key로 이어 씀).
- **예시 고르기(`pipeline/type_examples.py`)**: 사람 주 태그(HUMAN) 요구사항 중 지금 문서가 아닌 것, 정답지(answer_key_row) 문장과 정규화 글자가 같은 것은 뺀다. 지금 물을 줄과 예시 후보의 벡터를 `meaning.vectors`(text_vector 캐시)로 받아 코사인 0.80 이상 위에서 2개. 동점은 requirement_id 순(CR-11).
- **프롬프트**: 줄 끝에 ` (사람이 고른 예: "…" → TEST; "…" → COST)`. 예시 문장은 200자로 자름. 줄 번호 형식(A2)은 그대로라 줄 수 검사는 바뀌지 않는다. 프롬프트 판 p3 → p4(같은 파일도 새로 분석).
- **재현성**: 같은 입력이라도 사람 고침이 늘면 예시가 바뀐다. 처리 판에 예시 수를 남겨 실행 기록에서 보인다. 문서 재사용은 판이 같을 때만이므로 예시가 바뀐 뒤 같은 파일을 올리면 예전 결과를 다시 쓸 수 있다 [확인 필요: 예시 판까지 재사용 열쇠에 넣을지].
- **실패**: 벡터 실패(LLMFailure)면 예시 없이 묻는다.

## 대안

- 규칙(RULE) 줄을 예시로: 규칙이 이미 잡는 줄이라 AI가 배울 것이 적다.
- 정답지 줄을 예시로: K13 채점이 오염된다(정답을 보고 답함).

## 위험

- 사람 고침이 적으면 효과가 없다. 시연 때는 미분류 줄 몇 개를 고친 뒤 같은 고객사의 다른 문서를 돌려 보인다.
