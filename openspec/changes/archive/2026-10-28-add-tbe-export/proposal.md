# Proposal

## Why

목업 v4.57의 TBE 준수표(SCR-09)는 1차 입찰 뒤 고객과의 기술 평가(TBE) 미팅에서 요구사항마다 준수 여부를 함께 보는 표다.
판정과 원문 위치는 이미 있지만 이것을 표 한 장으로 모아 엑셀로 내려받는 기능이 없다(갭 G14, 결정 5 "TBE 먼저").
검토 상세 머리의 "TBE 준수표" 단추와 제출본 탭의 "이 판정으로 TBE 준수표 받기"도 지금은 잠겨 있다.

관련: FR-07(판정), FR-09(일탈·질의), CR-02·03(원문 위치 없으면 내보내지 않음), CR-06(팀 가정), CR-08(후보 표시), CR-11(같은 입력 같은 결과).

## What Changes

- TBE 준수표 줄 만들기: 현재 판정 중 준수·일탈 후보·질의 후보·확인 필요(보증값 작성은 데이터시트로)를 판정 순서대로, 항목·고객 요구·준수 여부·우리 제품값·원문 위치·확정/후보.
- 넣을 줄(후보 포함 / 확정한 줄만), 항목 언어(영문 / 국문 / 영문 + 국문) 선택. 원문 위치가 없는 판정은 넣지 않고 따로 센다.
- 같은 줄로 미리보기(JSON)와 엑셀 파일(.xlsx)을 만든다.
- 화면: SCR-09 TBE 준수표(`#/reviews/:id/tbe`). 검토 상세 머리 단추와 제출본 탭 링크를 연다.

## Non-Goals

- TBE 점수 예측, 고객 평가 결과 기록.
- 판정 기준 "제출본 v2 이상"(제출본은 v1 한 판, SCR-08-8_공유.md).
- 데이터시트 채우기(`add-datasheet-export`).

## Capabilities

### New Capabilities
없음.

### Modified Capabilities
- `bid-outputs`: TBE 준수표 엑셀.
- `review-workspace`: TBE 준수표 화면.

## Impact

- `backend/src/rfp_agent/pipeline/tbe.py`(새로), `api/runs.py`(`GET /runs/{id}/tbe`, `GET /runs/{id}/tbe/export`), 의존성 `openpyxl`.
- `frontend/src/views/Tbe.tsx`(새로), `App.tsx` 주소, `DetailBody`·`SubmTab` 링크.
