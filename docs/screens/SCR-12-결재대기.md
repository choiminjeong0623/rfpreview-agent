# 화면 명세: SCR-12 결재 대기 상세

- 연결 요구사항: FR-10, `review-approval` 승인 결정·상신 취소, `review-workspace` 판단 동작
- 기준 목업: `Spec2Win_목업_v4.57.html#Wait` (레이아웃 기준선)
- 구현 방식: 실제 (`update-approval-flow`)
- 주소: `#/reviews/{run_id}` — 검토가 승인 대기일 때 검토 상세 대신 이 화면이 보인다 (목업도 결재 대기 검토는 Wait 화면으로 연다)
- 사용 API: `GET /api/runs/{id}/approval`, `/judgments`, `/risks`, `/losses`, `/documents`, `/equipment`, `/history`, `GET /api/runs`, `POST /api/runs/{id}/approval`, `POST /api/runs/{id}/withdraw`
- 예정 API: 없음

## 화면 구성

| 영역 | 보이는 항목 | API 칸 | 비고 |
|---|---|---|---|
| 머리 줄 | 검토 번호, 단계, 마감 D-n, 상신 시각, 기안, 결재자 | `approval.requested_at·requested_by·approver` | |
| 제목 | 사업명 · 검토명, 이전/다음 결재 대기 | `GET /runs` 중 승인 대기 | 없으면 흐린 단추 |
| 알림 띠 | "○○의 결재를 기다리고 있습니다", 상신 후 n일(마감 지남·7일 넘음은 주황) | | 엔지니어: 상신 취소. 지정 결재자: "결재할 검토입니다" + 반려·승인 |
| 결재 의견 | 여러 줄 입력 (지정 결재자에게만) | — | 반려에는 필수 |
| 결재 진행 | 기안 → 결재 두 칸, 잠금 안내 | | |
| 상신한 내용 | 요구사항, 일탈 후보, 질의 후보, 확인 필요, 위험 조건, 손실 환산 가산액 / 상신 전 확인 결과 6줄 + 문서 읽기 점검 줄 / 상신 의견 | `reasons`, `review_ratio`, `submission_check.deviation_listed`, `read_unchecked` | AR-01 줄에 "일탈 목록에 n건" |
| 결재자가 볼 항목 | 일탈·질의 판정과 열린 위험 조건: 구분, 항목, 요구, 우리 제품값, 원문 위치 | `judgments`, `risks` | 반려한 판정·닫은 위험 조건은 뺀다 |
| 기본 정보 | 고객사, 국가, 비교 제품 | `RunSummary`, `equipment` | |
| RFP 문서 | 파일 이름 n개 | `documents` | |
| 처리 기록 | 결재 상신·상신 취소·승인·반려·다시 확인 (최신이 위) | `history` (검토 실행) | |

## 사용자 동작 → 시스템 반응

| 동작 | 누가 | 호출 API | 성공 시 | 실패 시 |
|---|---|---|---|---|
| 상신 취소 | 엔지니어 | `POST /withdraw` | 바로 검토 상세 판정 탭으로 이동하고 알림 "상신을 취소했습니다. 판정을 고친 뒤 다시 결재 상신해 주세요." | 오류 문장 (409 단계) |
| 승인 | 지정 결재자 | `POST /approval` APPROVED | 검토 상세(승인됨) | 403 지정되지 않은 결재자 |
| 반려 | 지정 결재자 | `POST /approval` REJECTED + 의견 | 검토 상세(반려됨) | 400 의견 없음 |
| 다른 승인자가 열기 | 승인자 | — | 읽기만, 띠에 "지정된 결재자(○○)만 결정할 수 있습니다" | — |

## 목업에 있지만 만들지 않는 요소

- 결재 요청 다시 알림, 열람 시각("열람함"), 사내 전자결재 번호, 참조, 첨부: `update-approval-flow` Non-Goal.

## 수용 기준 (Given / When / Then)

- **Given** 승인 대기 검토, **When** 지정 결재자가 열면, **Then** 상신 의견, 걸린 승인 기준, 일탈 후보 수, 목록에 들어간 수, 빠진 일탈이 보인다. (승인 화면)
- **Given** 승인자에게 상신된 검토, **When** 승인자가 내 할 일을 열면, **Then** 카드에 걸린 기준이 보이고 누르면 이 화면이 열린다. (엔지니어·승인자의 내 할 일)
