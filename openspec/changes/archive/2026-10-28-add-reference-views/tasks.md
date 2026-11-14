# Tasks

## 1. API

- [x] 1.1 pipeline: 제품표 조회(거르기·검색·빈 칸 수·팀 가정·쓰인 수), 제품 상세(쓰인 곳, 제안 포인트, 현장 이력)
- [x] 1.2 pipeline: 규칙 사전 조회 3종과 쓴 횟수
- [x] 1.3 `api/reference.py` 라우터: `/products`, `/products/{code}`, `/rules/compare`, `/rules/items`, `/rules/risk-expressions` (없는 제품 404)

## 2. 화면

- [x] 2.1 `api.ts` 타입과 함수
- [x] 2.2 SCR-16 제품표 화면 명세(`docs/screens/SCR-16-제품표.md`)와 화면
- [x] 2.3 SCR-17 판정 규칙 화면 명세(`docs/screens/SCR-17-판정규칙.md`)와 화면

## 3. 테스트 (Scenario마다 하나 이상, 이름에 Scenario 이름)

- [x] 3.1 제품군으로 거르기 / 빈 칸은 비어 있음 / 팀 가정 손실값
- [x] 3.2 판정에 쓰인 제품 / 쓰이지 않은 제품
- [x] 3.3 비교 방향 사전 / 위험 표현이 쓰인 횟수 / 같은 뜻 표현
- [x] 3.4 화면: 제품 상세 / 두 제품 비교 / 규칙 검색

## 4. 마무리

- [x] 4.1 `ruff`, `pytest`, `npm run lint`, `npm run build` 통과
- [x] 4.2 `openspec validate add-reference-views --strict` 통과 후 archive
