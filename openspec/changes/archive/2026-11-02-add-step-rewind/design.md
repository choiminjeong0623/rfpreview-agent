# 설계: add-step-rewind

## 결정

### 1. 흐름 안의 사람 동작 `rewind` (`pipeline/run.py`)
- `NEXT["engineer_review"]`에 처리 단계마다 갈 곳을 더하지 않고, 동작 `rewind`와 받은 단계(`step`)를 상태 `rewind_to`에 남겨 갈림 함수가 그 단계를 고른다. 갈림 후보(`add_conditional_edges`의 목적지 목록)에 `PIPELINE` 전부를 넣는다. 고르는 것은 코드다(CR-01).
- 흐름은 앞으로만 간다: engineer_review → (그 단계) → … → assign → engineer_review. 저장된 예전 상태를 잘라 내지 않아 흐름 기록에 그대로 남는다(add-flow-history가 "되돌려 다시 처리"로 보인다).
- **대안(버림)**: LangGraph time travel(예전 checkpoint에서 갈라 다시 돌리기). 갈라진 줄기가 생겨 흐름 기록·멈춘 자리 읽기가 복잡해지고, 그 뒤의 사람 동작 기록이 흐름에서 사라진다.

### 2. 사람 작업 이어받기
- 판정 노드는 이미 `carry_judgments`(같은 요구값·비교 제품·비교 규칙 줄의 확정·수정·반려), 위험 조건 노드는 `replace_risks`(같은 열쇠의 확인)를 늘 한다. 되돌리기는 같은 노드를 다시 돌리므로 따로 할 일이 없다.
- `record_revision`(개정 안내)은 문서 추가(`revision_pending`)일 때만이라 되돌리기에서는 개정을 만들지 않는다.
- 판정보다 앞(문서 읽기·같은 문서 찾기·위험 조건)부터 돌려도 처리한 문서는 같은 처리 열쇠로 다시 쓰여 요구사항 id가 같으므로 같은 줄이 이어진다.

### 3. 요청 (`pipeline/doc_add.py`와 같은 자리, `prepare_rewind`)
- 검사: 사용자 역할 ENGINEER(아니면 403), 단계 ENGINEER_REVIEW(아니면 409, "상신 취소 먼저"), 흐름 기록이 담당자 확인에서 멈춤(아니면 409), 단계 이름이 `PIPELINE`에 있음(아니면 400), 사유 비지 않음(400), 처음 파일 정보 있음(409).
- 통과하면 한 트랜잭션에서 단계 PROCESSING, 이력 `review_log`(target `review_run`, action `REWIND`, after `{step}`, reason). **[구현 때 바뀜]** `graph_state.rewind_pending`은 두지 않았다: 단계는 `run_to_end(rewind=)` 인자로 넘기고, 다시 처리 중 실패하면 흐름이 처리 중간에 멈춰 있어 다시 시도가 그 자리부터 잇는다. 이력 동작 제약에 `REWIND`를 더하는 마이그레이션 **0034**가 필요했다(계획에 빠짐). 백그라운드로 `run_to_end(run_id, paths, choices, rewind=단계)`.
- `execute_run(…, rewind=None)` → `graph_flow.start_input`: 담당자 확인에서 멈췄고 rewind가 있으면 `Command(resume={"action": "rewind", "step": 단계})`. 실행 기록 `resumed_from`에 그 단계(이어서 시작한 단계와 같은 칸).
- API `POST /api/runs/{id}/rewind {step, reason, actor_id}` → 202, `RunSummary`.

### 4. 화면 (`views/detail/LogTab.tsx`)
- 이력 표 위 한 줄: 단계 고르기(`STEP_NAMES`의 처리 단계), 사유 칸, [다시 처리]. 엔지니어 + 담당자 확인일 때만. 안내 "사람이 확정·수정한 판정은 같은 줄이면 그대로 이어받습니다".
- 누르면 `api.rewind` → 검토 요약을 다시 불러 처리 중 화면(기존 ProcessingView)이 뜬다. 끝나면 상세로 돌아오는 것은 기존 처리 중 화면 동작.
- 이력 문장(`components/history.ts`): `REWIND` → "{단계}부터 다시 처리". 흐름 기록 사람 동작 이름표 `rewind: '되돌려 다시 처리'`.

## 위험
- 다시 처리하는 동안 화면 다른 작업이 막힌다(처리 중 단계라 이미 막힘).
- 판정 규칙이 바뀌어 같은 줄 열쇠(비교 규칙)가 달라지면 그 줄의 확정은 이어지지 않는다. 문서 추가와 같은 한계이고, 이어받지 못한 줄은 "확인 전"으로 보여 사람이 다시 본다.
