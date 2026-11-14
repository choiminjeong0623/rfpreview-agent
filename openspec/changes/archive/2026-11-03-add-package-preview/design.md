# Design

## 결정

- **이미 있는 API만.** 숫자 칸·TBE 탭 = `GET /runs/{id}/tbe?base=v1&include=all&lang=ko`(제출본 v1 기준, counts·rows·assumed). 표지 = `GET /runs/{id}/equipment`(묶음 이름·판정 수·일탈 수) + 묶음마다 `GET /runs/{id}/judgments?group=&result=`의 전체 개수(준수·질의·확인 필요)와 확인 필요 줄 3개. 일탈·질의 = `GET /runs/{id}/outputs`(뺀 항목 제외). 견적 조건 = `GET /runs/{id}/cost-conditions`의 conditions. 영업 할 일 = `GET /assignments?role=SALES` 중 이 검토. 결재 줄 = `GET /runs/{id}/approval`.
- **숫자는 응답 값.** 화면은 세기만 하고 계산하지 않는다(CR-01). 팀 가정 = TBE 줄 중 `assumed` 수(CR-06).
- **창은 공통 `Modal`.** 넓은 창(`--uid-w: 960px`), 탭은 검토 상세 탭 모양(`.tabs`)을 쓰지 않고 창 안 작은 탭 줄. 표는 10줄씩 쪽 나누기(`usePage`).
- **자리.** `PackageActions` 상자에 [미리 보기]를 두어 제출본 탭과 사업 상세 창에 함께 생긴다. 창 안 내려받기는 같은 `PackageActions` 동작을 다시 쓰지 않고 zip 내려받기 단추 하나(진행 막대는 상자에서).
- **목업과 다른 곳.** 목업 "예시" 꼬리표와 "엑셀 내려받기"는 실제 데이터·zip이라 없앤다. 상태 칩은 "제출 준비" 대신 실제 단계 "결재 승인".

## 대안

- 시트 5개 엑셀: 백엔드 작업이 필요해 영업 요청이 있을 때 따로.
