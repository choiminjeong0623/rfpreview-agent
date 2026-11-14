# 화면 명세: SCR-09 TBE 준수표

- 연결 요구사항: FR-07(판정), FR-09(일탈·질의), `bid-outputs` TBE 준수표, `review-workspace` TBE 준수표 화면
- 기준 목업: `Spec2Win_목업_v4.57.html#Tbe`
- 구현 방식: 실제 (`add-tbe-export`). 화면 CSS는 목업 Tbe CSS 그대로(`frontend/src/mockup/Tbe.css`)
- 주소: `#/reviews/:id/tbe`. 검토 상세 머리 "TBE 준수표" 단추, 제출본 탭 "이 판정으로 TBE 준수표 받기"에서 연다
- 사용 API: `GET /runs/{id}`, `GET /runs/{id}/tbe?include=all|confirmed&lang=en|ko|both&base=now|v1`, `GET /runs/{id}/tbe/export`(같은 인자, .xlsx)

## 화면 구성

| 영역 | 보이는 항목 | API 칸 | 비고 |
|---|---|---|---|
| 머리 경로 | 홈 > RFP 검토 > 검토 번호 > TBE 준수표 | `review_no` | 검토 번호는 검토 상세로 연결 |
| 제목(`.ttl`) | TBE 준수표, 사업명 · 검토명 · 검토 번호 · 고객사, 검토 상세로, 엑셀 내려받기 | `project_name`, `review_name`, `customer_name` | 내려받는 동안 "만드는 중…" |
| 안내(`.sh-note`) | 목업 문구 그대로 | — | |
| 선택(`.sp`) | 판정 기준(현재 판정 (연 시각) / 제출본 v1), 넣을 줄(후보 포함 / 확정한 줄만), 항목 언어(영문 / 국문 / 영문 + 국문) | `base`, `include`, `lang` | 제출본 v1은 승인된 실행에서만 고를 수 있다. 승인 뒤 판정은 바뀌지 않아 현재 판정과 같다 |
| 요약(`.sh-sum`) | 넣는 줄, 준수, 일탈, 질의, 확인 필요, 그중 후보, 위치 없어 뺀 줄 | `counts` | |
| 미리보기 표(`.tb-t`) | No., Item(항목), 고객 요구, 준수 여부, 우리 제품값, 원문 위치(파일 / 절 · 표 · 행), 상태 | `rows` | 준수 여부 색: Comply 초록, Deviation 빨강, Clarification·To be confirmed 주황. 상태: 확정(초록) / 후보(회색), 팀 가정이면 아래에 "팀 가정". 10·20·50개씩 쪽 나눔 |
| 위치 없어 뺀 줄(`.tb-x`) | 뺀 수와 이유 | `no_location` | 0이면 숨김 |
| 알림(`.stt`) | "<파일 이름> 를 내려받았습니다 (n줄)." | — | 목업 문구 |

## 줄 규칙

- 넣는 판정: 현재 판정 중 준수·일탈 후보·질의 후보·확인 필요. 보증값 작성은 데이터시트(SCR-10)로, 반려한 판정은 뺀다.
- 순서: 일탈 → 질의 → 확인 필요 → 준수 (판정 탭과 같은 순서).
- 고객 요구·우리 제품값은 원문 그대로, 단위가 원문에 없으면 단위만 붙인다(CR-10). 제품값 뒤에 (제품 코드).
- 엑셀: 시트 TBE, 제목·안내 줄 뒤에 머리 줄. 영문 머리 No., Item, Requirement, Compliance, Offered, Source, Status. 원문 위치는 모든 위치를 줄바꿈으로.

## 수용 기준 (Given / When / Then)

- **Given** 판정 하나를 일탈로 고친 검토, **When** 검토 상세에서 "TBE 준수표"를 열고 "확정한 줄만"을 고르면, **Then** 넣는 줄 1, Deviation 한 줄, 파일 이름 "…_확정만.xlsx". (넣을 줄 바꾸기)
- **Given** TBE 준수표 화면, **When** "엑셀 내려받기"를 누르면, **Then** .xlsx가 내려받아지고 "…를 내려받았습니다 (n줄)." 알림. (엑셀 내려받기)
