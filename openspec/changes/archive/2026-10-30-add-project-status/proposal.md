# Proposal

## Why

목업 v4.57의 사업 현황(SCR-04)과 사업 상세(SCR-05)는 지금 고정 예시 데이터만 보여 준다(`add-example-screens`).
입찰 한 건(사업)은 Lot·설비 범위마다 검토를 따로 만들기 때문에, 입찰 기술 검토 엔지니어와 결재자는
"이 입찰의 범위들이 지금 어디까지 왔는지, 마감이 언제인지"를 검토 목록에서 하나씩 찾아봐야 한다.
2026-10-30 minjeong 요청: 사업 현황 백엔드·프런트를 실제 데이터로 만든다. 최종 발표(11-10) 전 기능 동결(11-04)에 맞춘다.

관련: FR-10(확인·승인 흐름), FR-11(협조 요청), `add-review-info` Non-Goal로 미뤘던 "사업 단위 화면, 고객 입찰 번호".
CR-04(없는 값은 비움), CR-08(확정은 사람), CR-11(판정 결과 영향 없음).

## What Changes

- 새 표 `business`(사업): 사업명, 고객사, 국가, 고객 입찰 번호, 발주 방식, 제출 마감일, 영업 담당, 만든 사람, 제출 완료 시각. 모두 사람이 넣는다.
- 검토를 사업에 연결한다(`review_run.business_id`). 검토 등록 때 "새 사업 만들기" 또는 "진행 중인 사업에 추가"를 고르고, 만든 뒤에도 연결·해제할 수 있다.
- 사업 진행 상태는 저장하지 않고 연결된 검토의 단계와 남은 협조 요청에서 코드로 계산한다(분석 중, 분석 실패, 판정 확인, 협조 대기, 결재 대기, 반려, 제출 준비, 제출 완료).
- "제출 완료"는 연결된 검토가 모두 승인된 뒤 사람이 표시한다. 취소할 수 있고 이력이 남는다.
- "내 사업": 머리글에서 고른 사용자가 연결 검토의 담당 엔지니어, 협조 요청 받은 사람, 지정 결재자, 영업 담당, 만든 사람 중 하나인 사업.
- 사업 정보 고침 이력.
- 화면: 사업 현황·사업 상세를 예시에서 실제로 바꾼다(지난 이력 탭은 예시로 남김). 검토 등록에 "사업 연결" 칸. 사업 상세 "이 사업에 RFP 등록".
- 이미 있는 검토는 마이그레이션에서 사업명 글자가 같은 것끼리 사업 하나로 묶는다.
- 시연용 사업 준비 명령(데모 RFP 3개).

## Non-Goals

- 기존 `project` 표(FR-06 값 불일치 비교 범위)와 `review_run.project_id`는 바꾸지 않는다.
- "등록 전 범위"(RFP는 받았지만 검토가 없는 Lot). 요약의 "등록 전 범위" 칸은 숨긴다.
- RFP에서 고객 입찰 번호·마감일·발주 방식을 자동으로 뽑기(원문 위치 필요, 별도 change).
- 입찰 금액, 개찰 결과, 지난 입찰 이력, 고객 측 연락처, 접속 상태(명세서 범위 밖).

## Capabilities

### New Capabilities
- `business-status`: 사업 만들기·고치기·이력, 검토 연결, 진행 상태 계산, 내 사업, 제출 완료 표시, 목록·상세 응답.

### Modified Capabilities
- `review-workspace`: 사업 현황·사업 상세 화면을 실제 데이터로, 검토 등록의 사업 연결, 예시 화면 목록에서 사업 현황·상세를 뺌.

## Impact

- DB: 마이그레이션 `0014_business.sql`(`business`, `business_log`, `review_run.business_id`, 기존 검토 묶기).
- CLI: `rfp-db demo-businesses`.
- API: `GET/POST /api/businesses`, `GET/PUT /api/businesses/{id}`, `POST/DELETE /api/businesses/{id}/submitted`, `GET /api/businesses/{id}/history`, `PUT /api/runs/{id}/business`, `POST /api/runs`·`/api/runs/library`에 사업 칸.
- 화면: `views/Projects.tsx`, `views/Project.tsx`(예시에서 옮김), `views/BusinessDialog.tsx`, `Register.tsx`, `ReviewDetail.tsx`, `openapi.json`·`api.gen.ts` 다시 생성.
- 판정·후보 계산은 바뀌지 않는다(CR-11 영향 없음).
