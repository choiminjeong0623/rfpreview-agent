# Tasks

## 1. DB

- [x] 1.1 `db/migrations/0014_business.sql`: `business`, `business_log`, `review_run.business_id`, 주석(`project`와 뜻 구분)
- [x] 1.2 같은 파일에서 기존 검토를 사업명 글자로 묶어 사업 만들고 연결

## 2. 백엔드 저장·계산 (`pipeline/business.py`)

- [x] 2.1 사업 만들기·고치기(사업명 필수, 영업 역할 검사, 바뀐 칸만 `business_log`), 사업명 고치면 연결 검토 `project_name` 맞춤
- [x] 2.2 검토 연결·해제(`review_log` EDIT, `project_name` 맞춤), 검토 시작(`start_run`)에서 `business_id`/`new_business_name` 받기
- [x] 2.3 범위 상태 계산 함수(design 3 표), 홈 협조 대기와 같은 기준
- [x] 2.4 목록(요약 3개, D-n, 내 사업·내 역할), 상세(범위·담당자·일정·문서)
- [x] 2.5 제출 완료 표시·취소(조건 409, 이력)

## 3. API

- [x] 3.1 `api/businesses.py` 경로와 `schemas.py` 응답 모델
- [x] 3.2 `PUT /api/runs/{id}/business`, `POST /api/runs`·`/runs/library` 칸, `RunSummary`·`RunListItem`에 `business_id`·`business_no`
- [x] 3.3 `cd frontend && npm run gen:api`

## 4. 화면

- [x] 4.1 사업 현황: `views/Projects.tsx`로 옮기고 API 연결, 예시 띠 지움, 등록 전 범위 칸 숨김, 반려 칩, 처리 중 새로고침
- [x] 4.2 사업 상세: 개요·담당자·일정·문서 실제, 지난 이력 예시 유지, 사업 정보 고치기 창, 제출 완료 단추, "이 사업에 RFP 등록"
- [x] 4.3 검토 등록: 사업 연결(새 사업 / 진행 중인 사업), 사업 값 미리 채우기, `#/register/business/<id>` 주소
- [x] 4.4 검토 머리글·목록의 사업명 링크, 연결된 검토는 검토 정보 창의 사업명 잠금
- [x] 4.5 `docs/screens/SCR-04`·`SCR-05` 명세와 `_공유.md`, `docs/screens/README.md` 구현 방식, `검수표.md` 다시 만들기

## 5. 시연 데이터

- [x] 5.1 데모 사업 준비 명령과 `docs/pull-and-run.md` 안내

## 6. 테스트 (Scenario마다 하나 이상, 이름에 Scenario 이름)

- [x] 6.1 사업 만들기 / 사업명 없이 만들기 / 영업이 아닌 영업 담당
- [x] 6.2 마감일 고치기 / 사업을 고쳐도 판정은 그대로
- [x] 6.3 새 사업을 만들며 검토 시작 / 진행 중인 사업에 추가 / 연결 해제 / 값 불일치 범위는 그대로
- [x] 6.4 협조 대기 / 협조가 끝난 담당자 확인 / 반려 / 상태 규칙 전부
- [x] 6.5 모두 승인된 사업 제출 완료 / 승인 전 제출 완료 거절 / 제출 완료 취소
- [x] 6.6 내 사업 거르기 / 협조 요청 받은 사람의 내 사업 / 요약 개수 / 사업 마감이 비었을 때
- [x] 6.7 담당자 모으기 / 문서 모으기 / 같은 사업명 묶기(마이그레이션)
- [x] 6.8 화면(e2e 또는 컴포넌트): 사업 현황 열기 / 반려 칩 / 팀 전체 / 범위 카드에서 검토로 / 이 사업에 RFP 등록 / 제출 완료 단추 / 지난 이력은 예시 / 사업 고르면 미리 채움 / 머리글에서 사업으로 / 예시 띠·저장하지 않음·금액 가림(기존 테스트 유지)

## 7. 마무리

- [x] 7.1 `ruff`, `pytest`, `npm run lint`, `npm run check:api`, `npm run build`, `openspec validate --all --strict`
- [x] 7.2 archive 후 PR

화면 Scenario는 `frontend/e2e/business-status.spec.ts`(CI 밖, 로컬에서 통과). 백엔드는 `backend/tests/test_business_status.py`.
