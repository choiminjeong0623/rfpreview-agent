## 1. 문서

- [x] 1.1 명세서 FR-11 ③④⑤⑥⑦ 영업 인계, 기획서 3-2 ⑪·4-1·부록 B
- [x] 1.2 SCR-10·SCR-08-8 화면 문서와 공유 문서

## 2. 백엔드

- [x] 2.1 마이그레이션 0020 `sales_handoff`
- [x] 2.2 `pipeline/sales_handoff.py`: 데이터시트 넘기기(후보 0, 엔지니어, 단계), 패키지 zip 만들기(승인 뒤), 패키지 보내기, 주소 없음·발송 실패 기록, 이력 SEND
- [x] 2.3 API: `POST /runs/{id}/datasheet/handoff`, `GET /runs/{id}/package`, `POST /runs/{id}/package/handoff`, `GET /runs/{id}/handoffs`, 응답 모델
- [x] 2.4 이력 탭에 `sales_handoff` 줄 문구
- [x] 2.5 테스트: 명세 Scenario마다

## 3. 프런트

- [x] 3.1 데이터시트 "영업에 넘기기" 풀기, 후보 막기 안내, 다시 넘기기·넘긴 시각
- [x] 3.2 제출본 탭 인계 패키지 내려받기·영업에 넘기기, 첨부 수, 마지막 기록
- [x] 3.3 `npm run gen:api`, e2e

## 4. 마무리

- [x] 4.1 `openspec validate --all --strict`, 검사 통과, archive
