# Design

## Context

기준 데이터는 `rfp-db` 적재 명령으로 `data/seed/`에서 DB에 들어간다(`reference-data`). 판정은 `judgment.product_code`, `judgment.compare_rule_id`,
위험 조건은 `risk_flag.expr_id`로 기준 데이터를 가리킨다. 현장 이력은 `fault_link`(항목 + 제품군 → 고장 사례)다. 지금 API에는 이 표들을 읽는 길이 없다.

## Decisions

### 1. API (읽기 전용, `api/reference.py` 라우터 하나)
- `GET /api/products?family=&q=&offset=&limit=`: 목록 줄 = 코드, 이름, 제품군, 주요 칸(전압, 전류, 단시간 kA, 주파수, 손실 3종, 중량), 설계 사례 카드, 출처, 빈 칸 수, 팀 가정, 판정에 쓰인 수. `X-Total-Count` 머리글(`add-review-info`와 같은 방식).
- `GET /api/products/{code}`: 전체 칸 + `used_in`(현재 판정: 실행 번호, 판정 id, 항목, 결과) + `proposals`(제안 포인트) + `field_history`(같은 제품군의 `fault_link` 줄과 고장 사례).
- `GET /api/products/families`: 제품군 탭과 위 요약 칸(제품 수, 빈 칸 있는 제품, 팀 가정 제품, 설계 사례 카드). 구현하며 더함.
- `GET /api/rules/compare`: `compare_rule` + `item_key.name_ko`, 쓴 판정 수(`judgment.is_current` 중 같은 `compare_rule_id`).
- `GET /api/rules/items`: `item_key` + `item_alias` 목록, 연결된 제품표 칸(`item_pm_mapping`), 그 항목을 쓴 현재 판정 수.
- `GET /api/rules/risk-expressions`: `risk_expression` + 쓴 횟수(`risk_flag.expr_id`).
- 대안: 화면이 판정 목록을 모아 집계 → 실행마다 불러야 해서 느리고, 실행에 묶이지 않은 제품은 볼 수 없다.

### 2. "판정에 쓰는 칸"과 빈 칸 수
- 판정에 쓰는 칸 = `item_pm_mapping`에 연결된 `product_master` 칸과 손실 3칸 중 그 제품군에 해당하는 것. 빈 칸 수는 그 칸들 중 NULL 개수.
- 구현 결정: "그 제품군에 해당하는 칸"은 그 제품군 제품 중 하나라도 값이 있는 칸으로 코드가 정한다(제품군별 칸 표가 따로 없음). 제품군 전체가 비운 칸은 그 제품군에 없는 칸으로 본다.
- 설명 글 칸(`description` 등)은 빈 칸 수에 넣지 않는다. 고정값(`company_fixed_value`) 항목은 제품 칸이 아니므로 빼고 따로 보여 준다.

### 3. 쓰인 횟수 기준
- 현재 판정(`is_current`)만 센다. "다른 제품으로 바꿔 보기" 전 판정은 세지 않는다.
- 모든 실행을 합쳐 센다. 실행을 고르는 거르기는 두지 않는다(목업 "이번 달 판정에 쓰임"은 기간 거르기가 필요해 뺌).

### 4. 화면
- SCR-16 제품표: 위 요약 칸(빈 칸, 팀 가정, 설계 사례 카드 수), 제품군 탭, 검색, 표(주요 10칸), 오른쪽 상세(연결 / 값 탭), 두 개 골라 비교.
- SCR-17 판정 규칙: 탭(비교 방향 / 위험 표현 / 항목 이름, 목업 순서), 검색, 표. 목업의 "수정 요청·규칙 추가" 버튼은 잠근 채 보인다(다른 화면과 같은 방식). 비교 방향의 강점 방향이 비면 판정처럼 항목 기본값을 보인다.
- 공통 규칙(`docs/screens/_공통규칙.md`)을 따른다. 팀 가정은 `Assumed`, 빈 칸은 "비어 있음".

## Risks / Trade-offs

- 쓰인 횟수를 요청마다 세므로 실행이 많아지면 느려질 수 있다 → 지금 규모(실행 수십 개)에서는 문제없고, 필요하면 색인을 더한다.
- 사전 판(`dict_version`)이 바뀌어도 화면은 지금 DB에 적재된 판만 보여 준다. 실행이 쓴 판과 다를 수 있다는 안내를 머리말에 둔다.
