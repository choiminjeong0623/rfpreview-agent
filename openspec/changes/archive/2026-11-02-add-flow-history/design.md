# 설계: add-flow-history

## 결정

### 1. 흐름 기록 읽기 (`pipeline/graph_flow.py` `history`)
- `graph.get_state_history(config(run_id))`로 저장된 상태(checkpoint)를 가져와 오래된 것부터 늘어놓는다. 상태마다 `next`(다음에 돌 단계)와 `values`(건수)와 `created_at`이 있다.
- 이웃한 두 상태 A → B에서 "돈 단계" = A의 `next[0]`, 끝난 시각 = B의 `created_at`, 걸린 시간 = B − A, 바뀐 값 = A와 B의 건수 차이. 처음 입력 상태(`__start__`)는 단계로 내지 않는다.
- 바뀐 값은 건수만: `*_count`와 문서 목록의 개수(`document_ids` → 문서, `readable_ids` → 읽은 문서). 파일 경로·사람 분류는 내지 않는다(설계 5장 "상태에는 작은 값만"과 같음).
- 사람 동작: 사람 단계를 지난 상태의 `values.action`(submit·approve·reject·withdraw·reopen·add_documents). 같은 동작이 다시 와도 단계마다 따로 남는다(상태가 단계마다 저장되므로).
- 멈춘 자리: 지금 `stop_of`와 같은 값(사람 단계 이름 / 처리 중간이면 `next_node` / END / 기록 없음).
- 읽기만 한다: `get_state_history`·`get_state`만 부르고 `invoke`·`update_state`는 부르지 않는다. 검토 단계 칸도 건드리지 않는다.

### 2. API
- `GET /api/runs/{run_id}/flow` → `RunFlow { run_id, recorded, stop, next_node, steps: [FlowStep { node, finished_at, seconds, changes: [FlowChange { key, before, after }], action }] }`. 검토가 없으면 404.
- `schemas.py`에 모델, `npm run gen:api`.

### 3. 화면 (`views/RunLog.tsx`)
- 펼친 줄의 `Steps` 아래에 `Flow` 부품. 펼칠 때만 `/flow`를 부른다(줄마다 한 번).
- 단계 이름은 `STEP_NAMES`(이미 있음) + 사람 단계 이름(담당자 확인·승인 대기·반려됨), 사람 동작 이름(상신·승인·반려·상신 취소·다시 확인·문서 추가), 바뀐 값 이름(판정·위험 조건·문서 등)은 `labels.ts`에 표를 더한다.
- 한 줄 모양: `판정 · 0.3초 · 판정 0 → 42`, 사람 동작은 `담당자 확인 · 상신`, 끝에 `담당자 확인에서 멈춤`. 색은 토큰만(`_프런트원칙.md`).
- `docs/screens/SCR-25_공유.md`에 한 줄.

## 대안
- 흐름 기록을 우리 표(run_step_time)에 따로 저장: 같은 내용을 두 곳에 두게 된다. checkpoint를 그대로 읽는다.
- checkpoint 표를 SQL로 직접 읽기: 직렬화 형식이 라이브러리 판에 묶여 버림. 라이브러리 API로 읽는다.

## 위험
- 흐름 기록이 길어질 수 있다(문서 추가·반려가 반복되면). 검토당 수십 줄이라 페이지 나누기는 하지 않는다.
- 단계 시간은 checkpoint 저장 시각 차이라 실행 기록의 단계별 시간(run_step_time)과 조금 다를 수 있다. 화면에 "흐름 저장 시각 기준"이라 적는다.
