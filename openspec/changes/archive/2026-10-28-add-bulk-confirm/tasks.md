# Tasks

## 1. API

- [x] 1.1 `review.bulk_confirm`: 단계·현재 판정 확인, 줄마다 확정·이력, 다시 만들기 한 번
- [x] 1.2 `POST /runs/{id}/actions/bulk` 라우터

## 2. 화면

- [x] 2.1 `api.ts` 타입과 함수
- [x] 2.2 판정 탭 고르기 칸과 한꺼번에 확정 띠 (SCR-08-1 명세·공유 갱신)

## 3. 테스트 (Scenario마다 하나 이상, 이름에 Scenario 이름)

- [x] 3.1 준수 모두 확정 / 현재 판정이 아닌 줄이 섞임 / 승인 대기 중 한꺼번에 확정
- [x] 3.2 화면: 고른 줄 확정 / 준수 모두 확정

## 4. 마무리

- [x] 4.1 `ruff`, `pytest`, `npm run lint`, `npm run build` 통과
- [x] 4.2 `openspec validate add-bulk-confirm --strict` 통과 후 archive
