# 화면 명세: SCR-08-7 지난 RFP 비교 탭

- 연결 요구사항: 명세서 8장 "지난 RFP 비교"(11-01 추가), `review-workspace` 지난 RFP 비교 탭, `review-run` 지난 검토 비교 대상·지난 검토 비교 (`add-past-compare`)
- 기준 목업: `Spec2Win_목업_v4.57.html#Detail` 지난 RFP 비교 탭 (`#cmp`)
- 구현 방식: 실제 데이터 (`add-past-compare`). 예전 예시 데이터(`update-review-screens` 묶음 9)는 지웠다
- 사용 API: `GET /api/runs/{id}/compare`(비교 대상), `GET /api/runs/{id}/compare/{other_id}`(달라진 요구)

## 화면 구성

| 영역 | 보이는 항목 | API 칸 |
|---|---|---|
| 머리(`.sech`) | 제목, 안내 문장, "비교 대상" 고르기("검토 번호 · 제목 (YY-MM)", 최근 것이 먼저 골라짐) | `targets[]`의 `review_no`, `project_name`, `review_name`, `started_at` |
| 지난 검토(`.cmph`) | 검토 번호(그 검토 상세로), 제목, "시작 날짜 · 판정 n줄 · 비교 제품", 단계 배지 | `target` |
| 건수 칸(`.cmpk`) | 달라진 요구 · 값 바뀜 · 새로 생김 · 사라짐 | 누르면 그 구분만 거른다(`aria-pressed`) |
| 표(`.tbl`) | 구분 배지, 항목(표준 항목 이름 + 설비 · 표의 항목 이름), 지난 RFP, 이번 RFP, 판정 변화(값 바뀜은 이전 → 이번, 사라짐은 "요구 없음"), 참고 | `rows[]`의 `kind`, `item_name`, `equipment`, `item_raw`, `before`, `after`, `before_result`, `after_result`, `note`. 사라진 줄은 흐리게 |
| 아래 문장 | "같은 요구 n줄은 값과 판정이 지난번과 같아 숨겼습니다." | `same` |
| 안내(`.cmempty`) | 고객사 없음: 검토 정보에 고객사를 넣으라는 안내 / 대상 없음: "고객사 "…"의 처리를 마친 다른 검토가 없습니다" / 다른 줄 없음: "요구 값·판정이 모두 같습니다" | `customer_name`, `targets` |

## 화면 상태

- 비교 대상을 바꾸면 거르기가 "달라진 요구"로 돌아간다. 저장하지 않는다.
- 짝짓는 동안 "짝짓는 중…".

## 수용 기준 (Given / When / Then)

- **Given** 같은 고객사로 처리를 마친 지난 검토가 있는 다음 입찰 검토, **When** 지난 RFP 비교 탭에서 "새로 생김"을 누르면, **Then** 지난 검토가 골라져 있고 예시 띠가 없으며 새로 생긴 요구만 남는다. (같은 고객사 지난 검토와 비교)
- **Given** 고객사를 넣지 않은 검토, **When** 탭을 열면, **Then** 고객사를 넣으라는 안내가 보인다. (고객사 없음 안내)
