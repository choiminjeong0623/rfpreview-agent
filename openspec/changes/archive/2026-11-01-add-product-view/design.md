# Design

## 1. 빠른 보기와 상세 화면이 같은 계산을 쓴다

`components/productSpec.ts`에 칸 목록(주요 칸·비교값 칸·손실 칸), 칸 하나 표시(`cell`: 해당 없음 "—", 빈 칸 "비어 있음", 팀 가정), 강점 방향(항목 사전 `pm_column`), 막힌 판정, 대신 쓸 제품을 둔다. 제품표 표·빠른 보기·비교·상세 화면이 모두 이것을 쓴다.

## 2. 막힌 판정

`used_in` 중 결과가 확인 필요(`NEEDS_REVIEW`)이고, 그 판정의 표준 항목(`item_key`)이 짝짓는 제품 칸(`/rules/items`의 `pm_column`)이 제품의 `empty_columns`에 든 줄. 그래서 `ProductUse`에 `item_key`를 더한다. `used_in`은 최근 100줄까지라 수도 그 안에서 센다(빠른 보기에 쓰는 수와 같다).

## 3. 지금 쓰이는 검토

`used_in`을 검토(`run_id`)로 묶어 결과별 수를 센다. D-day는 검토 마감(`due_date`, 없으면 안 보임). `used_runs`(전체 검토 수)는 머리 수로 쓴다.

## 4. 대신 쓸 수 있는 제품 (참고, 판정 안 바꿈)

`GET /products?family=<같은 제품군>&cards=false&limit=500`. 지금 제품 말고, 정격 전압이 같거나 높은 제품 가운데 (a) 막힌 칸에 값이 있으면 그 칸 이름, (b) 정격 전류·단시간 견딤 전류가 더 높으면 "단시간 50 kA (+10)"처럼 차이를 이유로 든다. 이유 수가 많은 순, 같으면 코드 순으로 2개. 숫자는 같은 단위 칸끼리만 비교(CR-10).

## 5. 요구 조건으로 찾기

켜면 지금 거르기(제품군·검색어·설계 사례)로 제품을 500개까지 한 번에 받아 화면에서 거른다(쪽 나누기도 화면). 조건: 정격 전압 ≥, 정격 전류 ≥, 단시간 ≥. 값이 빈 칸은 "값 없음"(맞음으로 치지 않음). 목업의 견딤 시간·피크 칸은 두지 않는다: 제품표에 견딤 시간 칸이 없고, 화면 명세 SCR-16 v4.96 표가 전압·정격 전류·단시간 셋만 정했다.

## 6. RFP 검토 찾기

`GET /runs`(최근 200)로 목록, 거르기는 화면(사업명·고객사 고르기, 진행 상태 전체·진행 중·끝남, 담당 전체·내 검토, 검토명·번호 검색). 요구값은 보이는 줄 8개까지 `GET /runs/{id}/judgments?limit=500`에서 표준 항목 `rated_voltage_um`·`rated_current`·`short_time_current` 줄의 `req_value_raw` 첫 값. 없으면 빈칸(CR-04).

## 7. CSS

`mockup/ProductsV496.css` = 목업 v4.96 Products·ProductView에서 지금 Main.css·Products.css에 없는 규칙 그대로(AI 요약 `.ais*`·글꼴 뺌). 상세 화면은 Products.css + ProductsV496.css.
