# Design

## 줄 만들기 (`pipeline/tbe.py`)

- `tbe(conn, run_id, include="all"|"confirmed", lang="en"|"ko"|"both")` → `{file_name, rows, counts, no_location}`. 미리보기 API와 엑셀이 같은 함수를 쓴다(CR-11).
- 판정은 `queries.run_judgments(priority=True)`로 모두 읽는다. 결과가 `WARRANTY_TO_FILL`이거나 `review_status = REJECTED`면 뺀다.
  보증값 작성 줄은 데이터시트(SCR-10)로 간다. 반려는 판정 칩 수와 같게 뺀다.
- 원문 위치가 없으면 `no_location`에 넣고 표에서 뺀다(CR-03). 판정은 위치 없이 만들지 않으므로 보통 0이다.
- 준수 여부 라벨: 영문 Comply / Deviation / Clarification / To be confirmed, 국문 준수 / 일탈 / 질의 / 확인 필요(목업 Tbe).
  "일탈 후보"가 아니라 "일탈"로 쓰는 것은 목업 그대로이며, 후보 여부는 상태 칸(확정 / 후보)으로 따로 보인다(CR-08).
- 항목: 영문 = `item_name_raw`(없으면 한글 이름), 국문 = `item_name`(없으면 원문). 둘 다 = 영문 + 아래 줄 국문.
- 고객 요구 = `req_value_raw` + `unit_raw` 원문 그대로(CR-10). 우리 제품값 = `product_value_raw` + 단위 + (제품 코드), 없으면 "—".
- 상태 = 확정(`CONFIRMED`·`EDITED`) / 후보. 팀 가정(`is_assumed`)이면 " · 팀 가정"을 붙인다(CR-06).
- 원문 위치: 첫 위치는 파일 이름과 "절 · 표 n번 · n행"으로 나눠 미리보기에 쓰고, 엑셀은 모든 위치를 줄바꿈으로 잇는다(`export.location_text`).

## 엑셀

- `openpyxl`. 시트 "TBE", 1행 제목(검토 번호 · 사업명), 2행 안내("Status 'Candidate'는 사람이 확정하지 않은 줄"), 4행 머리.
- 영문 머리: No., Item, Requirement, Compliance, Offered, Source, Status. 국문 머리: No., 항목, 고객 요구, 준수 여부, 우리 제품값, 원문 위치, 상태.
- 파일 이름 `TBE_<검토 번호>_후보포함|확정만.xlsx` (목업). 판정 기준이 제출본 v1이면 `TBE_<검토 번호>_v1_…`.

## 판정 기준

- 현재 판정 / 제출본 v1. 승인된 실행은 판정을 고칠 수 없어 둘이 같다(SCR-08-8). v1은 승인된 실행에서만 받고, 아니면 409.

## 화면

- 주소 `#/reviews/:id/tbe`, 목업 Tbe CSS(`mockup/Tbe.css`). 머리 경로: 홈 > RFP 검토 > 검토 번호 > TBE 준수표.
- 내려받기는 일탈 목록 초안처럼 fetch → blob → 저장, 끝나면 목업 알림 "<파일 이름> 를 내려받았습니다 (n줄)."
