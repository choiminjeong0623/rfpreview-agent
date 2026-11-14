# Tasks

## 1. 문서

- [x] 1.1 명세서 8장 "지난 RFP 비교", 기획서 부록 B
- [x] 1.2 SCR-08-7 화면 정의서·`SCR-08-7_공유.md`

## 2. 비교

- [x] 2.1 `pipeline/past_compare.py`: 비교 대상(같은 고객사), 판정 줄 짝짓기, 값 바뀜·새로 생김·사라짐, 참고 문장
- [x] 2.2 `GET /api/runs/{id}/compare`, `GET /api/runs/{id}/compare/{other_id}`, 응답 모델
- [x] 2.3 `npm run gen:api`
- [x] 2.4 테스트: Scenario마다 (`tests/test_past_compare.py`, 합성 문서 `build_judgment_spec_next`)

## 3. 화면

- [x] 3.1 지난 RFP 비교 탭 실제 데이터: 대상 고르기, 지난 검토 요약(검토 상세로), 건수 칸 거르기, 표, 숨긴 수, 고객사 없음·대상 없음 안내. 예시 데이터 지움
- [x] 3.2 e2e: 같은 고객사 두 검토 비교, 고객사 없음 안내
