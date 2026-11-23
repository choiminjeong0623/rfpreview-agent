# Design

## 1. 어디서 숫자를 가져오나 (CR-01·11)

새 계산을 하지 않고 이미 있는 함수 결과를 읽는다. 같은 데이터면 같은 요약이다.

| 칸 | 출처 |
|---|---|
| 판정 수 | `queries.judgment_counts` (`by_result`) — 요약 상자와 같은 수 |
| 팀 가정 | 현재 판정 중 `is_assumed` |
| 직접 작성할 칸 | 보증값 NOT_MAPPED 빈칸 수(update-review-ratio-hand-fill과 같은 셈) + 데이터시트 `empty` |
| 일탈·질의 | `screen_summary._deviations`와 같은 조건(현재·반려 아님), 질의는 `QUERY_CANDIDATE` |
| 상업 조건 | `cost_conditions.cost_conditions` 결과를 `kind`로 묶음 |
| 위험 조건 | 위험 조건 후보의 사람 확인 상태 |
| 남은 일 | `assignments_for(None)` 중 이 검토, 상태가 `DONE`이 아닌 것 |

원문 위치가 없는 줄은 넣지 않는다(CR-02). 값은 원문 문자열 그대로(CR-10), 없는 값은 "확인 필요"(CR-04).

## 2. 언제 만들 수 있나

담당자 확인·승인 대기·반려됨·승인. 승인 전이면 머리에 "결재 전 초안 — 판정이 바뀔 수 있습니다". 인계 패키지는 지금처럼 승인 뒤에만 만들고, 그때 영업 요약도 함께 든다.

## 3. 모듈

- `pipeline/sales_brief.py`: `sales_brief(conn, run_id) -> dict`, `sales_brief_docx(conn, run_id) -> (이름, 바이트)`. Word는 `export.py`와 같은 python-docx, 원문 위치는 `export.location_text`.
- `sales_handoff.build_package`가 zip 첫 파일로 넣는다.
- 응답 모양은 `schemas.SalesBrief`. 화면 타입은 `npm run gen:api`.

## 4. 대안

- AI로 요약 문장 쓰기: 숫자 대조 부담이 크고 영업에 필요한 건 표라서 버림.
- 인계 패키지 미리 보기 표지 탭을 고치기: 결재 전에는 열 수 없어 참여 판단에 늦음. 별도 API로 결재 전에도 내려받게 함.
- 엑셀 한 장: 영업이 출력·메일 붙임에 Word를 더 씀. 표 데이터는 이미 TBE·데이터시트 엑셀에 있음.

## 5. 위험

- 일탈이 수십 건이면 한 장을 넘는다 → 10건·5건으로 자르고 "외 n건"과 일탈 목록 Word 안내.
- 화면 숫자와 요약 숫자가 어긋날 수 있다 → 요약 상자·TBE와 같은 함수를 쓰고 테스트에서 비교.
