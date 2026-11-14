# Tasks

## 1. DB와 흐름

- [x] 1.1 마이그레이션 다음 번호: `approval`에 `requested_by`, `request_comment`, `withdrawn_at`, 결정 값 `WITHDRAWN`, 열린 승인 대기 행의 결재자 채우기
- [x] 1.2 review.py `finish_review`: 결재자·상신 의견 받기, 걸린 기준과 관계없이 승인 대기
- [x] 1.3 review.py `decide`: 지정 결재자만 결정
- [x] 1.4 review.py `withdraw`: 결정 전 상신 취소, 이력
- [x] 1.5 review.py `approval`·`my_tasks`: 상신 정보 응답, 승인자는 자기에게 온 검토만

## 2. API

- [x] 2.1 `POST /finish-review` 본문 `Submit`(400 의견·역할, 404 사용자)
- [x] 2.2 `POST /withdraw` 추가, `POST /approval`에 403(지정되지 않은 승인자)
- [x] 2.3 CLI·기존 호출부를 새 본문에 맞추기

## 3. 화면

- [x] 3.1 `api.ts` 타입과 함수(결재 상신, 상신 취소, 승인 화면 칸)
- [x] 3.2 결재 상신 창(요약, 상신 전 확인, 결재자, 상신 의견)
- [x] 3.3 승인 대기 화면(상신 정보, 상신 취소, 지정 결재자만 결정 버튼)
- [x] 3.4 e2e(`npm run e2e`) 흐름을 결재 상신으로 바꾸기

## 4. 테스트 (Scenario마다 하나 이상, 이름에 Scenario 이름)

- [x] 4.1 일탈 후보가 있는 실행 / 걸린 기준이 없는 실행 / 승인 대기 중 수정 / 확인 필요 비율 (기존 테스트를 새 흐름으로 고침)
- [x] 4.2 반려 / 승인자가 아닌 사용자 / 지정되지 않은 승인자
- [x] 4.3 결재자와 의견을 넣고 상신 / 상신 의견 없이 상신 / 승인자가 아닌 결재자
- [x] 4.4 결정 전 취소 / 승인된 뒤 취소
- [x] 4.5 화면: 승인 화면 / 결재 상신 창 / 견적 담당 내 할 일 / 엔지니어·승인자의 내 할 일 / 다른 결재자에게 간 검토

## 5. 마무리

- [x] 5.1 `ruff`, `pytest`, `npm run lint`, `npm run build` 통과
- [x] 5.2 `openspec validate update-approval-flow --strict` 통과 후 archive
