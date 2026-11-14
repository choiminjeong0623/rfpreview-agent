# Design

## 데이터시트 단위

- 고객 표 = `doc_table`(파일 + 표 이름). 판정이 하나라도 있는 표만 목록에 낸다. 고르는 키는 `table_id`.
- 줄 = 그 표의 현재 판정(반려 제외), `table_row.row_order` → `value_seq` 순서. 한 행에 값이 여럿이면 줄이 여럿이다.
  판정이 없는 행(값을 못 읽은 행)은 넣지 않는다. 그런 행은 문서 읽기 점검(SCR-08-2)에서 다룬다.

## 채운 값과 상태

| 판정 | 채운 값 | 근거 | 상태 |
|---|---|---|---|
| 보증값 작성 | 보증값 후보 값(+단위) | 회사 고정값 / 제품표 <코드> <칸> / 직접 입력 | 후보값 확정·직접 입력 = 확정, 후보 = 후보, 빈 후보·반려 = 확인 필요(이유: 보증값 후보 `reason_code`) |
| 그 밖 | 판정 제품값(+단위) (제품 코드) | 제품표 <코드> · 판정 이름(준수 아님일 때) | 판정 확정·수정 = 확정, 아니면 후보. 제품값이 없으면 확인 필요(이유: 판정 근거 글) |

- 단위는 원문에 없을 때만 붙인다(TBE와 같은 `_with_unit`). 팀 가정이면 근거에 "팀 가정".
- 줄의 "확정" 동작: 보증값 작성 줄은 `POST /actions`(warranty_candidate, CONFIRM), 그 밖은 판정 확정(judgment, CONFIRM). 새 API는 만들지 않는다.

## API

- `GET /runs/{id}/datasheets` → `[{table_id, table_name, file_name, rows, empty}]`.
- `GET /runs/{id}/datasheet?table_id=` → `{file_name, table_name, source_file, rows, counts}`. 다른 실행의 표면 404.
- `GET /runs/{id}/datasheet/export?table_id=` → .xlsx. 머리: 칸, Item, 항목, Unit, Requirement, Offered, Basis, Status.

## 화면

- 목업 Datasheet CSS. 머리 경로 홈 > RFP 검토 > 검토 번호 > 데이터시트 채우기.
- 목업에 없는 "데이터시트" 고르기를 보기 줄 앞에 둔다(실행마다 표가 여럿).
- 중복 칸 요약과 "중복 데이터시트 접기"는 만들지 않는다(공유 문서).
