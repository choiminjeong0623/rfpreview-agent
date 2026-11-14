# 설계: update-graph-stops

## 결정

### 1. checkpoint 저장소 = 같은 PostgreSQL
- `langgraph-checkpoint-postgres`의 `PostgresSaver`를 쓴다(`uv add langgraph-checkpoint-postgres`). 흐름 하나의 `thread_id`는 `run-<run_id>`.
- 저장소 표는 라이브러리가 자기 마이그레이션으로 만든다(`checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `checkpoint_migrations`). 우리 `db/migrations/` 번호 규칙과 섞지 않으려고 `migrate()` 끝에서 `PostgresSaver.setup()`을 부른다(`rfp-db setup`·`migrate`·테스트 DB 모두 이 함수를 지남). `CREATE INDEX CONCURRENTLY`가 있어 잠시 autocommit으로 돌린다.
- 대안: 직접 표를 만든 저장소(우리 마이그레이션 번호). 라이브러리 판이 바뀌면 직렬화 형식을 따라가야 해서 버림.
- 대안: 메모리 저장소. 서버를 다시 켜면 멈춘 자리를 잃어 버림.

### 2. 흐름 모양
```
documents → pairs → risks → judge → (출력 단계들) → meaning
  → engineer_review ⟲ (interrupt)
       ├ submit        → approval
       └ add_documents → documents
  approval (interrupt)
       ├ approve  → END
       ├ reject   → rejected
       └ withdraw → engineer_review
  rejected (interrupt)
       └ reopen   → engineer_review
```
- 갈림은 `add_conditional_edges`에 사람 동작 이름 → 다음 노드 표를 둔다(코드 분기, AI가 고르지 않음).
- 사람 노드 안: `interrupt({"stop": "ENGINEER_REVIEW"})`로 멈춤 → 이어 갈 때 받은 동작 이름을 상태(`action`)에 남기고, 갈림 표가 다음 노드를 고른다. 표에 없는 동작은 오류.
- **[구현 때 바뀜]** 처음 계획은 노드 안에서 `finish_review` 같은 함수를 부르는 것이었으나, 함수 쪽에서 흐름을 잇는 것으로 바꿨다. 사람 동작 함수(`finish_review`, `decide`, `withdraw`, `reopen`)가 지금처럼 검사·기록·단계 바꾸기를 한 뒤, 같은 트랜잭션 끝에서 `graph_flow.advance(conn, run_id, 동작)`을 부른다. 이유: API·CLI·테스트 어디서 함수를 불러도 흐름이 같이 움직이고(빠뜨릴 길이 없음), 검사에서 거절되면 흐름을 건드리기 전에 끝나며, 흐름을 잇다 실패하면 트랜잭션이 되돌려 단계 칸도 그대로 남는다.
- 단계 칸은 함수가 지금처럼 바꾼다. 화면이 읽는 단계 칸이 그대로 진실의 한 곳이고, 흐름은 같은 자리에 멈춰 있다.

### 3. API는 그대로
- API 끝점은 바꾸지 않는다. 흐름 잇기는 위 함수 안에서 한다. 흐름 기록이 없으면(예전 검토) `advance`는 아무것도 하지 않는다.
- 흐름 저장은 처리 트랜잭션과 따로 바로 남겨야 해서, 같은 DB로 자동 커밋 연결을 하나 더 연다(`conn.info.dsn` + `password`). 흐름이 그 동작을 받는 자리에 있지 않으면 409로 거절하고, 호출한 함수의 트랜잭션이 되돌린다.
- 문서 추가는 지금처럼 끝점이 `prepare_add`로 검사·기록을 하고 백그라운드 작업(`execute_run`)이 돈다. `execute_run`은 흐름이 담당자 확인 자리에 있으면 `add_documents`(처음 파일 + 더한 파일)로 이어 가 문서 처리부터 다시 돈다. 같은 줄 확정 이어받기(`carry_judgments`, `replace_risks`)는 지금 노드 그대로.

### 4. 이어서 다시 시도
- 실패·취소한 흐름은 마지막으로 끝난 단계의 checkpoint가 남는다. `prepare_retry`가 검사·기록을 하고, `execute_run`이 흐름이 처리 중간에 멈춰 있으면 `invoke(None, config)`로 이어 간다. 저장된 흐름이 없으면 지금처럼 처음부터. 노드는 다시 돌아도 되게 이미 만들어져 있다(실패한 노드의 쓰기는 되돌려지고, 위험 조건·판정 노드는 이전 결과를 바꿔 쓴다).
- `graph_state.resumed_from`에 이어서 시작한 노드 이름, `graph_state.skipped_steps`에 건너뛴 단계 수를 적는다. 실행 기록 응답(`RunLogItem`)에 `resumed_from`을 더한다.
- 같은 입력이면 같은 결과(CR-11): 건너뛴 단계의 결과는 DB에 이미 있고 흐름 상태에는 건수만 있다.

### 5. 상태에 담는 것
- `RunState`는 지금처럼 작은 값(run_id, 경로, 분류, 건수)만. 큰 결과는 DB 표에 있다. checkpoint 크기는 검토당 수 KB.

## 위험
- 라이브러리 판 고정: `langgraph-checkpoint-postgres`가 `psycopg-pool`을 끌어온다. 서버는 요청마다 새 연결을 쓰므로 저장소도 그 연결로 만든다(풀 안 씀).
- 흐름과 단계 칸이 어긋날 수 있음(예: 손으로 DB를 고침). `resume`은 흐름이 멈춘 자리와 단계 칸이 다르면 409로 거절하고 로그를 남긴다.
- 테스트 시간: 사람 노드 시험은 가짜 AI로 짧은 합성 문서를 쓴다.

## 확인 방법
- 끝 단계(뜻 찾기)에서 일부러 실패시킨 뒤 다시 시도하면 AI 호출 수가 처음 실행보다 적고, 결과(판정·위험 조건 수)는 처음부터 돌린 것과 같다.
- 실제 RFP로 처음부터 vs 이어서 다시 시도 시간 비교는 로컬 [확인 필요].
