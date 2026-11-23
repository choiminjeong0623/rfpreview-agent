# Design: update-run-fencing

## Context

- 실행 토큰은 `review_run.run_token`(0042). `run_queue.enqueue`와 `reclaim`이 새 토큰을 `UPDATE review_run`으로 쓴다. 이 UPDATE는 검토 행에 행 잠금을 건다.
- 처리 흐름(`pipeline/run.py`)은 `check_cancel`로 토큰을 **읽고 비교만** 한다(`_set_step`, 문서 처리 중 `report`). 그 뒤 단계가 결과를 쓰고 `conn.commit()`할 때는 다시 보지 않는다.
- 단계 안의 커밋 자리는 여러 곳이다:
  - 노드 끝의 `conn.commit()`(`_pairs_node`, `_judge_node`, `_meaning_node`, `_step_node`, `_documents_node`)
  - `with conn.transaction():` 블록 끝(`_risks_node`, 문서 저장)
  - 단계가 부르는 함수 안의 `conn.commit()`(예: `outputs.py`, `document.py`)
  - 문서 병렬 처리 스레드의 연결(`graph_flow.open_like`)
- 마지막 결과(담당자 확인·실패)는 이미 `WHERE run_token = %s` 조건이 붙은 한 문장이라 안전하다.
- 빈틈 예: `_judge_node`는 `_set_step`에서 토큰을 본 뒤 `judge_run`(수백 줄 INSERT) → `carry_judgments` → `commit`. 그 사이에 다시 시도가 들어오면 옛 실행의 판정이 저장되고, 옛 실행은 다음 `_set_step`에서야 멈춘다.

## Goals / Non-Goals

- Goal: 처리 흐름의 모든 커밋이 "그 순간 토큰이 자기 것일 때만" 저장되게 한다. 확인과 저장을 같은 트랜잭션·같은 잠금 아래에서.
- Goal: 고치기 전에 실패하고 고친 뒤 통과하는 테스트로 보인다.
- Non-Goal: 살아 있음 판단, 흐름 상태(checkpoint) 저장, 화면·API, 마이그레이션.

## Decisions

### 1. 커밋 직전에 행을 잠그고 토큰을 다시 읽는다

`ensure_owned(conn, run_id, token)`:

```sql
SELECT run_token::text FROM review_run WHERE run_id = %s FOR UPDATE
```

다르면 `RunSuperseded`를 내고, 부른 쪽 트랜잭션은 되돌려진다(`_execute`의 예외 처리가 이미 `conn.rollback()` 후 `"SUPERSEDED"`를 돌려준다). 같으면 잠금을 쥔 채 커밋한다. 커밋하면 잠금이 풀린다.

- 순서: 옛 실행이 먼저 잠그면 `enqueue`의 UPDATE는 커밋이 끝날 때까지 기다리고, 그 뒤 새 실행이 같은 줄 이어받기(FR-10 ⑤, 이미 있음)로 결과를 바꾼다. `enqueue`가 먼저면 옛 실행의 `FOR UPDATE`는 새 토큰을 읽고 되돌린다. 어느 쪽이든 "밀려난 실행의 결과가 남는 일"은 없다.
- 잠금을 쥐는 시간은 커밋 직전 한 문장뿐이라, 다시 시도 API가 AI 응답 시간만큼 기다리는 일은 없다.
- 교착: 옛 실행이 그 트랜잭션에서 이미 검토 행을 UPDATE했으면(진행 기록 등) 잠금을 이미 쥐고 있어 같은 결과다. `enqueue`는 `run_job`과 `review_run`만 건드리고 결과 표는 건드리지 않으므로 서로 다른 순서로 두 자원을 잡는 경우가 없다.

### 2. 실행 연결의 `commit()`을 감싼다 (`OwnedConnection`)

`execute_run`이 `ctx.token`이 있으면 `ctx.conn`을 얇은 감싸개로 바꾼다. 감싸개는 모든 속성을 원래 연결에 넘기고, `commit()`만 `ensure_owned` 뒤 원래 `commit()`을 부른다. `graph_flow.open_like`도 감싼 연결을 받으면 감싼 연결을 돌려준다(문서 병렬 처리 스레드).

- 이렇게 하면 단계가 부르는 함수(`outputs`·`document`·`meaning` 등) 안의 `conn.commit()`도 고치지 않고 같은 규칙을 따른다. 그 함수들은 사람 동작(API)에서도 쓰이는데, 그때는 감싸지 않은 연결이라 지금과 같다.
- `with conn.transaction():`의 바깥 블록은 `commit()`을 부르지 않고 psycopg 안에서 커밋한다. 처리 흐름에서 이렇게 커밋하는 자리(`_risks_node`, 문서 저장의 바깥 트랜잭션)는 블록 마지막 문장으로 `ensure_owned`를 부른다. 구현할 때 처리 흐름이 부르는 모듈의 `transaction()`을 모두 찾아 바깥 블록인지 본다(tasks 2.3).
- 토큰 없이 부른 실행(CLI `rfp-review run`, 예전 테스트)은 감싸지 않는다. 지금과 같다.

### 3. 테스트는 고치기 전에 실패해야 한다

`test_run_queue.py`에 "단계 저장 직전에 밀려남":

1. 대기열에 넣고 `claim`으로 옛 작업을 꺼낸다(토큰 A).
2. `judge_run`을 감싸, 판정 줄을 쓴 뒤 돌아가기 전에 **다른 연결**(autocommit)로 `enqueue`해 토큰 B를 쓰게 한다.
3. 옛 실행을 `execute_run(ctx(token=A))`로 돌리면 `"SUPERSEDED"`, 그 검토의 판정 0건.
4. `drain`으로 새 작업을 돌리면 담당자 확인, 판정은 새 실행 것만.

고치기 전 코드에서는 3번의 판정이 0건이 아니어서 실패한다. PR 설명에 실패 출력과 통과 출력을 함께 남긴다. 문서 병렬 처리 연결 쪽은 같은 방식으로 `_save_run_document` 앞에서 다시 넣는 테스트 하나를 더 둔다.

## 버린 대안

| 대안 | 버린 이유 |
|---|---|
| 노드 끝 커밋만 `commit_owned()`로 바꿈(계획 문서 첫 안) | 단계가 부르는 함수 안의 커밋과 문서 병렬 연결의 커밋이 빠진다 |
| 결과를 쓰는 문장마다 `WHERE run_token = …` 조건 | 결과 표 수십 곳의 INSERT를 고쳐야 하고, INSERT에는 조건을 붙이기 어렵다. 빠뜨리기 쉽다 |
| 단계 시작에 행을 잠그고 단계 내내 쥠 | AI 응답을 기다리는 몇 분 동안 다시 시도·취소 API가 멈춘다 |
| DB 제약 트리거(지연 트리거로 커밋 때 검사) | 결과 표마다 트리거와 세션 변수가 필요해 마이그레이션이 커지고, 사람 동작 API의 쓰기와 구분하기 어렵다 |

## Risks / Trade-offs

- 흐름 상태(checkpoint)는 LangGraph 저장기가 따로 쓴다. 노드가 커밋에서 `RunSuperseded`로 멈추면 그 노드의 흐름 상태는 저장되지 않으므로 새 실행이 옛 흐름 상태를 이어받는 일은 없다. 다만 앞 노드까지의 흐름 상태는 남아 있고, 새 실행은 지금처럼 자기 입력으로 흐름을 다시 시작하거나 멈춘 단계부터 잇는다(변화 없음).
- AI 호출 기록(`trace.flush`)도 실행 연결로 커밋되므로, 밀려난 뒤의 호출 기록은 남지 않는다. 지금도 실패·취소 때는 `_execute`가 따로 남기므로 그 동작은 그대로 둔다.
- 커밋마다 한 문장이 늘지만 단계 하나에 커밋은 몇 번뿐이다.
