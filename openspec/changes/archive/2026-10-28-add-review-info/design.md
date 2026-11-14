# Design

## Context

`review_run`에는 실행 번호, 시작한 사람(`started_by`), 단계, 사전 판, 흐름 상태만 있다. 스키마 v1의 `project` 표는
"값 불일치 비교 범위"를 위한 문서 묶음이라(FR-06) 사람이 붙이는 검토 이름과는 뜻이 다르다. 로그인은 없고 화면에서 사용자를 고른다.
목업 v4.57은 검토 목록·홈·상세·결재 머리글에 검토 번호, 검토명(사업명 + 설비 범위), 고객사·국가, 제출 마감(D-day), 담당 엔지니어를 보여 준다.

## Decisions

### 1. 저장 위치: `review_run`에 칸 추가
- 마이그레이션 다음 번호(현재 0009): `project_name VARCHAR(200)`(사업명), `review_name VARCHAR(200)`(검토명 = 설비 범위), `customer_name VARCHAR(200)`, `country VARCHAR(60)`,
  `due_date DATE`, `engineer_id INT REFERENCES app_user(user_id)`. 모두 NULL 허용.
- 대안: `project` 표를 넓혀 실행과 잇기 → `project`는 문서 묶음 판단(파일 3~8 확인 전 등)에 쓰이고 있어 뜻이 섞인다.
  사업 단위 화면은 Non-Goal이라 지금은 실행에 바로 둔다. 나중에 사업 화면을 만들면 그때 `project`와 잇는다.
- 국가는 자유 글자(목록 고르기는 화면에서 최근 값 추천 정도). 국가 코드표는 만들지 않는다.

### 2. 사람이 넣는 값이라 원문 위치를 붙이지 않음
- CR-02·03은 "시스템이 만드는 값"에 원문 위치를 요구한다. 검토 정보는 사람이 넣고 판정에 쓰지 않으므로 위치 칸이 없다.
- 언어 모델·규칙이 문서에서 채우는 일은 하지 않는다(Non-Goal). 자동 추출을 만들면 그때 위치·신뢰도 칸을 함께 둔다.

### 3. API
- `POST /api/runs`: 지금 `files`만 받는 multipart 폼에 `project_name`, `review_name`, `customer_name`, `country`, `due_date`(YYYY-MM-DD),
  `engineer_id`, `actor_id`를 선택 칸으로 더한다.
- `POST /api/runs/library`: 본문(`LibraryRun`)에 같은 칸을 더한다.
- `PUT /api/runs/{id}/info`: 본문 `ReviewInfo`(여섯 칸 + `actor_id`). 보낸 칸만 바꾸고, 빈 문자열은 비우기로 본다.
  바뀐 칸만 `review_log`에 `target_table='review_run'`, `action='EDIT'`, `before_value`/`after_value`로 남긴다. 사유는 받지 않는다(판정 수정이 아님).
- 응답(`RunSummary`, `RunListItem`): `review_no`, `project_name`, `review_name`, `customer_name`, `country`, `due_date`, `engineer_id`, `engineer_name`.
  `RunListItem`에는 `requirements`, `risks`, `deviation_candidates`, `proposals`를 더한다. 개수 SQL은 요약과 같은 식을 함수 하나로 모아 같이 쓴다.
- 검토 번호는 저장하지 않고 응답 때 만든다: `RV-{started_at 연도}-{run_id:03d}`. 실행 번호가 1000을 넘으면 네 자리 그대로.
- 전체 개수: `GET /requirements`, `/judgments`, `/warranty`는 응답 본문(배열)은 그대로 두고 `X-Total-Count` 머리글을 더한다.
  본문을 `{items, total}`로 바꾸면 화면과 테스트가 모두 깨지므로 머리글로 한다. Vite 프록시는 머리글을 그대로 넘긴다.

### 4. 검증
- 담당 엔지니어는 `role='ENGINEER'`만(아니면 400). 없는 사용자는 404.
- 마감일은 날짜 형식만 검사한다. 지난 날짜도 받는다(이미 마감 지난 검토를 나중에 등록할 수 있음).
- 검토 정보는 단계와 관계없이 고칠 수 있다. 승인 대기 중 잠기는 것은 판정·후보이지 검토 정보가 아니다.

### 5. 화면
- 시작 칸(파일 올리기 옆): 검토명, 고객사, 국가, 마감일, 담당 엔지니어(엔지니어 사용자 고르기, 기본 = 고른 사용자).
- 실행 고르기를 목록 표로 바꾼다: 검토 번호, 단계, 검토명(없으면 첫 파일 이름), 고객사·국가, 담당, 마감(D-day), 시작, 요구사항·위험·일탈·제안 수.
- D-day는 화면에서 오늘 날짜로 계산한다(D-0 = 오늘, 지나면 "마감 지남").
- 검토 머리글: 검토 번호 · 검토명 · 고객사 · 마감 D-day · 담당, 연필 버튼으로 고치기.

## Risks / Trade-offs

- 실행 단위로 저장하므로 같은 RFP를 다시 돌리면 검토 정보를 다시 넣어야 한다 → 화면이 "직전 실행 정보 복사"를 제공하는 것은 후속으로 둔다.
- `project`와 따로 두어 나중에 사업 화면을 만들 때 옮기는 작업이 생긴다. 칸 5개라 옮기기 비용은 작다.
- `X-Total-Count`는 본문만 보는 클라이언트가 모를 수 있다 → `api.ts`에 머리글을 읽는 함수를 따로 둔다.

## 결정 기록

- 2026-10-28 (구현 중): 목업 v4.57은 검토 목록에 "사업명"과 "설비 범위"를 따로 두고, 등록 화면에서 검토명을 "사업명 · 설비 범위"로 만든다.
  목업과 같게 하려고 `project_name`(사업명)을 더하고 `review_name`은 설비 범위로 쓴다. 화면 제목은 `사업명 · 검토명`(한쪽이 비면 있는 쪽만). [결정]
  사업명은 자유 글자이고 `project` 표와 잇지 않는다(사업 화면은 Non-Goal).
