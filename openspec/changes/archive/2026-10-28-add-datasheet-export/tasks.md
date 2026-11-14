# Tasks

## 1. API

- [x] 1.1 `pipeline/datasheet.py`: 데이터시트 목록, 한 장(채운 값·근거·상태), 엑셀
- [x] 1.2 `GET /runs/{id}/datasheets`, `/datasheet`, `/datasheet/export`

## 2. 화면

- [x] 2.1 `api.ts` 타입과 함수
- [x] 2.2 SCR-10 데이터시트 채우기 화면 명세(`docs/screens/SCR-10-데이터시트.md`)와 화면, 공유 문서
- [x] 2.3 검토 상세 머리 "데이터시트 채우기" 단추

## 3. 테스트 (Scenario마다 하나 이상, 이름에 Scenario 이름)

- [x] 3.1 보증값 후보 칸 / 근거 없는 빈 칸 / 판정 제품값 칸 / 데이터시트 엑셀
- [x] 3.2 화면: 칸 확정 / 확인 필요만 보기

## 4. 마무리

- [x] 4.1 `ruff`, `pytest`, `npm run lint`, `npm run build` 통과
- [x] 4.2 `openspec validate add-datasheet-export --strict` 통과 후 archive
