# Tasks

## 1. DB와 저장

- [x] 1.1 마이그레이션 다음 번호: `review_run`에 `project_name`, `review_name`, `customer_name`, `country`, `due_date`, `engineer_id` 추가
- [x] 1.2 pipeline: 실행 시작(`start_run`)이 검토 정보를 받아 저장, 담당 엔지니어 기본값(시작한 엔지니어)과 역할 검사
- [x] 1.3 pipeline/review.py: 검토 정보 고치기(바뀐 칸만 `review_log` EDIT)

## 2. API

- [x] 2.1 `POST /api/runs` 폼 칸, `POST /api/runs/library` 본문 칸 추가
- [x] 2.2 `PUT /api/runs/{id}/info` 추가 (400 역할, 404 사용자·실행)
- [x] 2.3 `RunSummary`·`RunListItem` 응답에 검토 번호·검토 정보·담당 이름, 목록에 개수 4개 (요약과 같은 개수 함수)
- [x] 2.4 요구사항·판정·보증값 목록에 `X-Total-Count` 머리글

## 3. 화면

- [x] 3.1 `api.ts` 타입과 함수(검토 정보, 전체 개수 읽기)
- [x] 3.2 검토 시작 칸에 검토 정보 입력
- [x] 3.3 검토 목록 표(검토 번호, 검토명 대체, 고객사·국가, 담당, D-day, 개수)
- [x] 3.4 검토 머리글 표시와 고치기

## 4. 테스트 (Scenario마다 하나 이상, 이름에 Scenario 이름)

- [x] 4.1 검토 정보와 함께 시작 / 검토 정보 없이 시작 / 엔지니어가 아닌 담당자
- [x] 4.2 마감일을 바꿈(이력 1건) / 판정은 그대로
- [x] 4.3 목록의 개수 / 검토 번호
- [x] 4.4 판정 목록 나눠 받기(전체 개수)
- [x] 4.5 화면: 목록에서 마감 보기 / 검토명이 빈 검토 / 머리글에서 고치기 (컴포넌트 테스트 또는 e2e)

## 5. 마무리

- [x] 5.1 `ruff`, `pytest`, `npm run lint`, `npm run build` 통과
- [x] 5.2 `openspec validate add-review-info --strict` 통과 후 archive
