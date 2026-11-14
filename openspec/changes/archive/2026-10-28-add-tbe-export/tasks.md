# Tasks

## 1. API

- [x] 1.1 `openpyxl` 의존성
- [x] 1.2 `pipeline/tbe.py`: 줄 만들기(넣을 줄·언어·위치 없는 줄), 엑셀
- [x] 1.3 `GET /runs/{id}/tbe`, `GET /runs/{id}/tbe/export` (판정 기준 v1은 승인된 실행만)

## 2. 화면

- [x] 2.1 `api.ts` 타입과 함수
- [x] 2.2 SCR-09 TBE 준수표 화면 명세(`docs/screens/SCR-09-TBE준수표.md`)와 화면, 공유 문서
- [x] 2.3 검토 상세 머리 "TBE 준수표" 단추, 제출본 탭 링크

## 3. 테스트 (Scenario마다 하나 이상, 이름에 Scenario 이름)

- [x] 3.1 후보 포함 / 확정한 줄만 / 엑셀 파일 / 항목 언어
- [x] 3.2 화면: 넣을 줄 바꾸기 / 엑셀 내려받기

## 4. 마무리

- [x] 4.1 `ruff`, `pytest`, `npm run lint`, `npm run build` 통과
- [x] 4.2 `openspec validate add-tbe-export --strict` 통과 후 archive
