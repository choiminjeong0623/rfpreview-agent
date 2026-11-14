# Design

## Context

- 스키마 v1의 `project` 표는 사업 화면용이 아니다. `data/seed/document_catalog.csv`의 `project_key`(파일 1·2 = P-A, 19~22 = P-D)로
  "사업 P-A" 같은 줄이 적재되고 `document.project_id`가 붙는다. `pipeline/risk.py`는 같은 키의 문서끼리만 값 불일치를 비교한다(FR-06).
  `pipeline/run.py`는 검토 문서가 모두 같은 키면 `review_run.project_id`를 자동으로 채운다.
- `review_run`에는 사람이 넣는 검토 정보(사업명 글자, 설비 범위, 고객사, 국가, 마감, 담당 엔지니어)가 있다(`add-review-info`, 0009).
  홈 "사업별"은 이 사업명 글자로 묶는다.
- 로그인은 없고 머리글에서 사용자를 고른다. "내 할 일"·결재자 지정만 사람별이다.
- 목업 v4.57 Projects·Project 화면과 CSS는 예시 화면(`views/examples/Projects.tsx`, `Project.tsx`, `examples/SCR-04.ts`)으로 이미 있다.

## Goals / Non-Goals

목표는 사업 현황·사업 상세·등록 화면 사업 연결을 실제 데이터로 바꾸고 11-03까지 머지하는 것. Non-Goal은 proposal과 같다.

## Decisions

### 1. 새 표 `business` (10-30 minjeong 결정)
- `project`를 넓히지 않고 따로 둔다. `project` = FR-06 비교 범위(기준표), `business` = 사람이 만드는 사업. 마이그레이션 주석과 이 문서에 적는다.
- 대안: `project`에 칸을 더하고 `origin`으로 구분 → 기준 줄이 사업 목록에 섞일 수 있고 `run.py` 자동 연결이 사람이 고른 연결을 덮어써서 버림.
- `0014_business.sql`:
  - `business(business_id SERIAL, business_name VARCHAR(200) NOT NULL, customer_name VARCHAR(200), country VARCHAR(60), tender_no VARCHAR(80), order_mode VARCHAR(200), due_date DATE, sales_id INT → app_user, created_by INT NOT NULL → app_user, created_at TIMESTAMPTZ, submitted_at TIMESTAMPTZ, submitted_by INT → app_user)`
  - `business_log(log_id, business_id, field, before_value JSONB, after_value JSONB, actor_id, acted_at)` — `review_log`는 `run_id NOT NULL`이라 쓸 수 없다.
  - `ALTER TABLE review_run ADD COLUMN business_id INT REFERENCES business(business_id)`.
  - 기존 검토 묶기: `project_name`이 비지 않은 검토를 `trim(project_name)` 글자 그대로 묶어 사업을 만들고 연결. 만든 사람·고객사·국가·마감은 가장 먼저 시작한 검토 값. 대소문자·띄어쓰기 차이는 묶지 않는다(글자 일치).
- 번호 표시: `PJ-{created_at 연도}-{business_id:03d}`, 저장하지 않음. 화면 주소는 이 번호로 받는다(`#/projects/PJ-2026-003`).

### 2. 검토 사업명 맞추기
- 연결하면 `review_run.project_name`을 사업명으로 바꾼다(검토 이력 EDIT). 사업명을 고치면 연결 검토의 `project_name`도 바꾼다.
  홈 "사업별", 검토 목록, 검토 머리글이 고치지 않아도 같은 이름을 보인다.
- 고객사·국가·마감은 검토마다 따로 둔다(Lot마다 마감이 다를 수 있음). 등록 화면에서 사업 값으로 미리 채울 뿐이다.

### 3. 진행 상태 계산 (`pipeline/business.py`의 함수 하나)
| 조건 (위에서부터 처음 맞는 것) | 상태 키 | 화면 |
|---|---|---|
| 사업 `submitted_at` 있음 | `done` | 제출 완료 |
| `PROCESSING` | `an` | 분석 중 |
| `FAILED` | `fail` | 분석 실패 |
| `ENGINEER_REVIEW` + `assignment.status = 'TODO'` 1건 이상 | `co` | 협조 대기 |
| `ENGINEER_REVIEW` | `chk` | 판정 확인 |
| `APPROVAL` | `ap` | 결재 대기 |
| `REJECTED` | `rej` | 반려 (목업에 없음, 빨간 칩, `SCR-04_공유.md`) |
| `APPROVED` | `sub` | 제출 준비 |
- 홈의 "협조 대기" 열과 같은 기준(확인하지 않은 TODO 협조 요청)을 쓴다. 상태 SQL은 `pipeline/business.py`의 `STATE` 하나.
- 사업 전체 진행 여부: `submitted_at`이 없으면 진행 중. D-n은 서버가 `CURRENT_DATE` 기준으로 계산(`days_left`), 마감이 비면 연결 검토 최소 `due_date`.

### 4. 내 사업과 내 역할
- `user_id`를 받으면 다음 중 하나라도 맞는 사업: 연결 검토 `engineer_id`, `assignment.assignee_id`, 취소되지 않은 `approval.approver_id`, `business.sales_id`, `business.created_by`.
- 역할 하나: 엔지니어 → 결재자 → 협조 → 영업 → 만든 사람. 화면은 "Lot 1 기술 검토" 같은 긴 글 대신 역할 이름만 보인다(`SCR-04_공유.md`).

### 5. 제출 완료
- `POST /api/businesses/{id}/submitted`: 연결 검토 1개 이상, 모두 `APPROVED`가 아니면 409. `DELETE`로 취소. 둘 다 `business_log`.
- 누를 수 있는 사람은 따로 막지 않는다(로그인 없음). 이력으로 남긴다.

### 6. API (`api/businesses.py`, 응답 모델은 `schemas.py`)
- `GET /api/businesses?user_id=&scope=mine|all` → `BusinessList{summary{open, due3, overdue}, items[BusinessListItem]}`
- `GET /api/businesses/{id}` → `BusinessDetail`(정보, `ranges[]`, `people[]`, `schedule[]`, `documents[]`)
- `POST /api/businesses`, `PUT /api/businesses/{id}`(보낸 칸만, 빈 문자열은 비우기), `GET /api/businesses/{id}/history`
- `PUT /api/runs/{id}/business` 본문 `{business_id | null, actor_id}`
- `POST /api/runs`(폼)·`/api/runs/library`(본문)에 `business_id` 또는 `new_business_name`(둘 다 오면 400)
- `RunSummary`·`RunListItem`에 `business_id`, `business_no` 추가 → `npm run gen:api`.
- 오류: 사업 없음 404, 영업 역할 아님 400, 사업명 빔 400, 제출 조건 409.

### 7. 화면
- 예시 파일을 `views/Projects.tsx`·`views/Project.tsx`로 옮기고 데이터만 API로 바꾼다. CSS·마크업은 그대로(목업 대조 `compare-mockup.mjs` 유지).
- 찾기(상태·국가·마감·검색어)는 지금처럼 화면에서 거른다. 사업 수가 적어 서버 거르기는 하지 않는다.
- 사업 상세 일정 탭: 사업 마감, 검토마다 시작·상신·결정 날짜. 목업의 "Addendum 받음, 질의 마감, 개찰" 같은 일정은 없음(`SCR-05_공유.md`).
- 지난 이력 탭은 `SCR-04.ts`의 예시 일부를 남기고 탭 안에 예시 띠.
- 등록 화면: 목업 "사업 연결" 라디오 두 개. 주소 `#/register/business/<id>`면 두 번째를 고른 채 연다(화면 주소에 물음표 쿼리를 쓰지 않는 앱 틀 규칙).
- 검토 머리글·검토 목록의 사업명은 연결이 있으면 사업 상세 링크.

### 8. 시연 데이터
- `rfp-db demo-businesses --business <사업명> a.docx [b.docx …] [--customer …] [--due-in 14]`: `--business`마다 사업 하나, 파일마다 검토 하나(설비 범위 = 파일 이름)를 끝까지 돌린다.
  담당은 기본 엔지니어. 데모 파일(프로젝트 파일 `demo-tests/files/`)은 저장소에 없으므로 경로를 인자로 받는다. 키가 없으면 AI 없이 돈다.

## Risks / Trade-offs

- 글자 일치 묶기는 "Thai Binh"와 "Thai Binh " 같은 차이를 다른 사업으로 만든다 → `trim`만 하고, 사업 상세에서 연결을 옮길 수 있다.
- 사업명과 검토 사업명을 맞추므로 검토 머리글에서 사업명을 고치면 연결과 어긋난다 → 연결된 검토는 검토 정보 창에서 사업명 칸을 잠그고 "사업 상세에서 고치기" 링크.
- 상태를 매번 계산하므로 사업이 많으면 느려질 수 있다 → 시연 규모(수십 건)에서는 문제없음. 필요하면 뷰로 바꾼다.
- 기능 동결(11-04) 전 시간이 모자라면: 등록 화면 연결 → 사업 상세 "검토 연결"로 대체 → 일정 탭 예시 유지 순으로 줄인다.

## Open Questions

- 제출 완료를 누를 수 있는 역할을 영업·결재자로 좁힐지 [확인 필요] — 지금은 막지 않음.

## 결정 기록

- 2026-10-30 (구현 중): 협조 대기 기준을 "끝나지 않은(DONE 아님)"에서 "확인하지 않은(TODO)"으로 바꿨다. 홈 화면 "협조 대기" 열이 TODO만 세므로 같은 검토가 두 화면에서 다른 상태로 보이지 않게 했다. 명세 문장도 고쳤다.
- 2026-10-30 (구현 중): 등록 화면 주소를 `#/register?business=<id>` 대신 `#/register/business/<id>`로 했다.
- 2026-10-30 (구현 중): 연결된 검토의 사업명은 검토 정보 창에서 잠그고(400), 사업 상세에서만 고친다. 사업명을 고치면 연결 검토의 사업명도 바꾸고 검토 이력에 남긴다.
- 2026-10-30 (구현 중): 범위 카드의 "Lot" 자리는 Lot 칸이 없어 "범위 n"(하나면 "단일 발주")으로 보인다. 일정 탭에는 검토 마감(RUN_DUE)도 넣었다.
