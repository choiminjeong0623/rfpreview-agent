# Proposal

## Why

목업 v4.57의 데이터시트 채우기(SCR-10)는 고객 데이터시트 양식의 칸 순서대로 우리가 써 낼 값(보증값)을 채우고, 근거와 확정 여부를 보여 주며
엑셀로 내려받는 화면이다. 보증값 후보(FR-08)와 판정의 제품값은 이미 있지만 고객 표 하나 단위로 모아 보거나 내려받을 곳이 없다(갭 G14, 3-11).
로드맵 5번의 두 번째 내려받기다.

관련: FR-08(보증값 후보), FR-07(판정 제품값), FR-10(확정), CR-02(원문 위치), CR-04(없는 값은 비움), CR-06(팀 가정), CR-08(후보), CR-10(단위 환산 금지).

## What Changes

- 데이터시트 목록: 실행의 판정이 있는 고객 표마다(파일 + 표 이름) 칸 수와 빈 칸 수.
- 데이터시트 한 장: 표의 판정 줄을 원문 행 순서대로, 칸 번호·항목·단위·고객 요구·채운 값·근거·상태(확정 / 후보 / 확인 필요).
  요구값이 빈 칸(보증값 작성)은 보증값 후보, 나머지는 판정의 제품값을 채운 값으로 쓴다. 값이 없으면 비워 두고 확인 필요.
- 같은 줄로 엑셀 파일(.xlsx).
- 화면: SCR-10 데이터시트 채우기(`#/reviews/:id/datasheet`), 보기 거르기, 줄마다 확정. 검토 상세 머리 "데이터시트 채우기" 단추.

## Non-Goals

- 영업에 넘기기(전달 대상·받는 화면이 없음). 단추는 잠근다.
- 다른 섹션의 같은 칸(중복 데이터시트) 찾기.
- 비어 있는 칸을 화면에서 바로 채우기. 지금처럼 판정 탭 패널에서 넣는다.

## Capabilities

### New Capabilities
없음.

### Modified Capabilities
- `bid-outputs`: 데이터시트 엑셀.
- `review-workspace`: 데이터시트 채우기 화면.

## Impact

- `backend/src/rfp_agent/pipeline/datasheet.py`(새로), `api/runs.py`(`GET /runs/{id}/datasheets`, `/datasheet`, `/datasheet/export`).
- `frontend/src/views/Datasheet.tsx`(새로), `App.tsx`, `DetailBody.tsx`.
