# 화면 명세

목업을 바로 코드로 옮기지 않고, 화면마다 **화면 명세(SCR-xx)**를 먼저 쓴 뒤 구현한다.
백엔드가 "요구사항(FR) → 스펙(OpenSpec) → 구현"을 하듯, 프런트는 "목업 → 화면 명세 → 구현"을 한다.
화면 명세의 수용 기준은 구현할 때 OpenSpec change의 `review-workspace` Scenario와 화면 테스트로 옮긴다.

| 파일 | 내용 |
|---|---|
| `README.md` (이 파일) | SCR 번호표, 화면–FR–API 연결표 |
| `_공통규칙.md` | 모든 화면에 같은 것: 화면 상태 4종, 라벨표, 형식, 권한, 예시 화면 규칙 |
| `_템플릿.md` | 화면 명세 하나의 틀 |
| `_디자인.md` | 목업 CSS 쓰는 법, 색·글꼴 토큰, 공통 부품 |
| `_프런트원칙.md` | 프런트 폴더·상태 관리·이름·토큰·공통 부품·오류 처리·테스트 규칙 |
| `SCR-xx_공유.md` | 목업과 피할 수 없이 다르게 만든 곳과 이유 (팀 공유용) |
| `SCR-xx-<이름>.md` | 화면별 명세 (SCR-00, 02~08, 08-1~08-12, 09~13, 16, 16-1 작성) |
| `_v4.96_결정.md` | 목업 v4.96 반영 결정 6개, 새로 필요한 API, 구현 순서 (2026-11-01) |
| `검수표.md` | 목업과 앱을 나란히 찍은 대조 결과 (v4.57, v4.96 배치 점검) |
| `../추적표.md` | 자동 생성: FR → OpenSpec 시나리오 → 화면 수용 기준 → 구현 컴포넌트 → 테스트. 설정은 `../추적_연결.json`, `cd frontend && npm run trace` |

## 기준 목업

- **2026-11-01부터 기준은 `Spec2Win_목업_v4.96.html`**(화면 26개, 새 화면 `JudgeView` 판정 상세·`ProductView` 제품 상세). 같은 폴더에 있다. v4.57과 달라진 점과 만들지 않는 것은 `_v4.96_결정.md`와 각 화면 명세의 "v4.96 바뀐 점" 장에 있다. 대조 결과 전체는 공유 폴더 `gap-list/갭목록_목업v4.96_vs_API.md`.
- `Spec2Win_목업_v4.57.html` 한 파일에 24개 화면이 들어 있다. 화면은 주소 뒤 화면 키로 연다: `…v4.57.html#Detail`.
- 목업 파일은 `docs/screens/mockup/Spec2Win_목업_v4.57.html`에 둔다(5.5 MB). 브라우저로 열면 오른쪽 아래 "화면 목록"으로 화면을 바꿀 수 있다. 새 판이 오면 같은 폴더에 판 번호를 붙여 더하고, README의 기준 판을 바꾼다.
- 목업은 **레이아웃 기준선**이다. 값 종류(문서 종류, 요구사항 유형, 할 일 상태)와 라벨은 목업이 아니라 API를 따른다(2026-10-28 결정, `_공통규칙.md` 2장).
- 목업과 API의 차이 전체는 갭 목록(공유 폴더 `gap-list/갭목록_목업v4.57_vs_API.md`)에 있다.

## 1. SCR 번호표

구현 방식
- **실제**: 지금 API로 만든다.
- **실제 + 예정**: 일부 칸이 승인된 change(`add-review-info`, `update-approval-flow`)의 API를 기다린다. 그 칸은 change가 archive될 때까지 비워 둔다.
- **일부 예시**: 화면은 실제로 만들되, API가 없는 영역만 예시 데이터로 보여 준다.
- **예시 화면**: 백엔드 없이 목업처럼 예시 데이터로만 보여 준다(2026-10-28 결정: 로그인, 입찰 이력, 팀 공유, 설정). 예시 화면 규칙은 `_공통규칙.md` 5장.

| SCR | 목업 화면 키 | 화면 이름 | 메뉴 | 연결 FR·스펙 | 구현 방식 |
|---|---|---|---|---|---|
| SCR-00 | (모든 화면) | 앱 틀: 왼쪽 메뉴, 머리글, 화면 주소 | — | `review-workspace` 앱 틀 | 실제. 알림은 예시 (`SCR-00-앱틀.md`) |
| SCR-01 | `Login` | 로그인 | — | 범위 밖 (로그인 없음, 사용자 고르기) | 예시 화면 (`add-example-screens`) |
| SCR-02 | `Loading` | 처리 상태 | — | FR-01~06, `review-run` | 실제 |
| SCR-03 | `Home` | 홈 | 홈 | FR-10, FR-11, `review-workspace` 홈 화면 | 실제 (내 업무·카드·실패 알림·팀 업무). 공지·자료실·행사는 예시 |
| SCR-04 | `Projects` | 사업 현황 | RFP 관리 | `add-project-status` | 실제 (`add-project-status`) |
| SCR-05 | `Project` | 사업 상세 | RFP 관리 | `add-project-status` | 실제. 지난 이력 탭만 예시 |
| SCR-06 | `Main` | 검토 목록 | RFP 관리 | FR-10, `add-review-info` | 실제 + 예정 |
| SCR-07 | `Register` | 검토 등록 | RFP 관리 | FR-01, `add-review-info` | 실제 + 예정. 자동 추출 확인(2단계)은 일부 예시 |
| SCR-08 | `Detail` | 검토 상세 | RFP 관리 | 아래 SCR-08-x | 탭별로 다름 |
| SCR-08-12 | `JudgeView` | 판정 상세 (v4.96 새 화면) | 검토 상세 안 | FR-07·08·09·10, CR-02 | 실제 + 예정 (`add-judgment-view`, `add-query-sent`) |
| SCR-09 | `Tbe` | TBE 준수표 | 검토 상세 안 | FR-07, FR-09, `add-tbe-export` | 실제 (미리보기·엑셀 내려받기) |
| SCR-10 | `Datasheet` | 데이터시트 채우기 | 검토 상세 안 | FR-08, `add-datasheet-export`, `add-submission-package` | 실제 (칸 확정·엑셀 내려받기·영업에 넘기기) |
| SCR-11 | `Fail` | 분석 실패 상세 | RFP 관리 | CR-12, `review-run` AI 오류 처리 | 실제 (단계·오류 문장). 재시도 방법 고르기·처리 기록은 일부 예시 |
| SCR-12 | `Wait` | 결재 대기 상세 | RFP 관리 | FR-10, `update-approval-flow` | 실제 + 예정 |
| SCR-13 | `Todo` | 협조 요청 | RFP 관리 | FR-11, `role-assignment` | 실제 (부서별 요청·메일 보내기·회신 받음). v4.96 검색·RFP별·재요청·내보내기는 예정(`update-todo-search`), 요청하기는 예시 창 |
| SCR-14 | `Bids` | 입찰 이력 | RFP 관리 | 범위 밖 (금액은 가격 범위) | 예시 화면 (`add-example-screens`) |
| SCR-15 | `BidView` | 입찰 상세 | RFP 관리 | 범위 밖 | 예시 화면 (`add-example-screens`) |
| SCR-16-1 | `ProductView` | 제품 상세 (v4.96 새 화면) | 제품표 안 | `reference-data`, FR-07·14·15 | 실제, 읽기 전용. 입찰 결과만 예시 |
| SCR-16 | `Products` | 제품표 | 지식 관리 | `reference-data`, FR-07 근거, FR-13, FR-15, `add-reference-views` | 실제 (읽기 전용). 엑셀·요구 조건으로 찾기 잠김, 제품 카드 창 없음 |
| SCR-17 | `Rules` | 판정 규칙 | 지식 관리 | `reference-data`, FR-05·06·07 사전, `add-reference-views` | 실제 (읽기 전용). 사람이 제안한 표현은 예시, 단위 탭 없음 |
| SCR-18 | `Phrases` | 표준 문구 | 지식 관리 | 없음 (일탈·질의 문장은 FR-09에서 언어 모델이 씀) | 예시 화면 (`add-example-screens`) |
| SCR-19 | `Eval` | 정답지·채점 | 지식 관리 | K1~K13, `add-evaluation`, `add-requirement-answer-key` | 실제 |
| SCR-20 | `Team` | 팀 현황 | 팀 공유 | 범위 밖 | 예시 화면 (`add-example-screens`) |
| SCR-21 | `Notice` | 공지사항 | 팀 공유 | 범위 밖 | 예시 화면 (`add-example-screens`) |
| SCR-22 | `SysNotice` | 시스템 공지 | 팀 공유 | 범위 밖 | 예시 화면 (`add-example-screens`) |
| SCR-23 | `Files` | 자료실 | 팀 공유 | 범위 밖 | 예시 화면 (`add-example-screens`) |
| SCR-24 | `Settings` | 설정 | 설정 | 범위 밖 | 예시 화면 (`add-example-screens`) |
| SCR-25 | (목업에 없음) | 실행 기록 | 지식 관리 | NFR-09, `add-run-log` | 실제 (`SCR-25_공유.md`) |

### SCR-08 검토 상세의 탭

검토 상세는 머리글(검토 정보·요약 칸)과 탭 9개, 창 3개로 되어 있어 탭마다 명세를 나눈다. 머리글은 SCR-08 본문에 쓴다. v4.96부터 탭 줄은 판정·위험 조건·문서 읽기 점검·상업 조건·이력 5개와 "더 보기"(손실 환산·입찰 영향·지난 RFP 비교·제출본)이고, 판정 줄을 누르면 판정 상세 화면(SCR-08-12)으로 간다.

| SCR | 탭·창 | 연결 FR·스펙 | 구현 방식 |
|---|---|---|---|
| SCR-08 | 머리글, 요약 칸 | FR-07·09·13, `add-review-info` | 실제 + 예정 |
| SCR-08-1 | 판정 (표 + 오른쪽 판정 상세) | FR-07, FR-08, FR-10, FR-12 | 실제. 번역·질의 보냄 표시는 없음 |
| SCR-08-2 | 문서 읽기 점검 | FR-01·02 (읽지 못한 곳) | 실제 (표·그림·단위·위치, 확인 기록) |
| SCR-08-3 | 위험 조건 | FR-06, `add-rule-suggestion` | 실제 (사전에 추가 제안 포함) |
| SCR-08-4 | 손실 환산 (참고) | FR-13 | 실제 |
| SCR-08-5 | 입찰 영향 | FR-14, FR-15, FR-09 | 실제 |
| SCR-08-6 | 상업 조건 | FR-16, `add-cost-conditions` | 실제 |
| SCR-08-7 | 지난 RFP 비교 | `add-past-compare` | 실제 |
| SCR-08-8 | 제출본 | FR-10 (승인 뒤 확정) | 실제 (승인 기록, 사본 없음) |
| SCR-08-9 | 이력 | FR-10 수정 이력 | 실제 |
| SCR-08-10 | 결재 상신 창 | FR-10, `update-approval-flow` | 실제 + 예정 |
| SCR-08-11 | 일탈 목록 초안 · 질의서 초안 (Word 내려받기, 문장 고치기) | FR-09, FR-10 | 실제 |
| SCR-08-12 | 판정 상세 화면 (v4.96, 판정 창을 대신함) | FR-07·08·09·10 | 실제 + 예정 |

## 2. 화면–FR–API 연결표

"예정"은 승인된 change에서 생길 API, "없음"은 아직 어떤 change에도 없는 것이다. 응답 칸 이름은 `frontend/src/api.ts` 타입을 따른다.

| SCR | 지금 있는 API | 예정 API | 없음 (예시 데이터 또는 빼기) |
|---|---|---|---|
| SCR-02 | `GET /runs/{id}` (`stage`, `step`) | — | 진행률 %, 남은 시간 |
| SCR-03 | `GET /runs`, `GET /assignments?role=`, `GET /users` | — | 판정 기준 변경 영향, 재시도, 게시판, 행사, 접속 상태 |
| SCR-06 | `GET /runs` | 검토 번호·검토 정보·개수·담당 (`add-review-info`) | 같은 입찰 묶기 |
| SCR-04 | `GET /businesses` | — | 등록 전 범위 |
| SCR-05 | `GET`·`PUT /businesses/{id}`, `POST`·`DELETE /businesses/{id}/submitted` | — | 지난 입찰 이력, 고객 측 창구, 접속 상태 |
| SCR-07 | `POST /runs`, `GET /library`, `POST /runs/library`, `GET /businesses` | 검토 정보 입력 칸 (`add-review-info`), 사업 연결 (`add-project-status`) | 자동 추출, Lot 나누기 |
| SCR-08 | `GET /runs/{id}`, `/documents`, `/equipment`, `/losses`, `/approval`(preview) | 검토 정보 고치기 `PUT /runs/{id}/info` | 문서 추가, 상신 권장일 |
| SCR-08-1 | `GET /judgments`, `/requirements/{id}`, `/checks`, `/risks`, `/outputs`, `/history`, `POST /actions`, `PUT /equipment/{group}/product` | 전체 개수 `X-Total-Count` | 번역, 질의 보냄 상태, 한꺼번에 확정 |
| SCR-08-2 | `GET /read-checks`, `POST`·`DELETE /read-checks/{key}` | — | — |
| SCR-08-3 | `GET /risks`(`item_name`), `/history`, `/documents`, `POST /actions` | — | 사전 추가 제안 (예시 영역) |
| SCR-08-4 | `GET /losses`, `PUT /losses/{id}` | — | 직접 협조 요청 |
| SCR-08-5 | `GET /proposals`, `GET /judgments`, `POST /actions`, `GET /equipment`, `PUT /equipment/{group}/product` | — | — |
| SCR-08-9 | `GET /history` | — | 시스템 처리 기록 |
| SCR-08-10 | `GET /approval`, `GET /submission-check`, `GET /users` | 결재자·상신 의견 `POST /finish-review` (`update-approval-flow`) | 참조자, 첨부 |
| SCR-08-11 | `GET /outputs`, `GET /outputs/export`, `POST /actions` | — | — |
| SCR-08-12 | `GET /judgments`, `/requirements/{id}`, `/documents`, `/rules/compare`, `/products/{code}`, `/checks`, `/outputs`, `/history`, `/warranty`, `POST /actions` | 원문 줄 범위 (`add-judgment-view`), 질의 보냄 (`add-query-sent`) | 번역, 과거 입찰 결과 |
| SCR-09 | `GET /runs/{id}`, `/tbe`, `/tbe/export` | — | — |
| SCR-10 | `GET /runs/{id}`, `/datasheets`, `/datasheet`, `/datasheet/export`, `POST /actions` | — | 성적서 근거, 중복 칸, 영업에 넘기기 |
| SCR-11 | `GET /runs/{id}` (`failed_step`, `error_message`), `/documents` | — | 멈춘 위치·원문, 이어서 재시도, 처리 기록 |
| SCR-12 | `GET /approval`, `POST /approval`, `/outputs`, `/risks`, `/history` | 상신 정보·상신 취소 `POST /withdraw` (`update-approval-flow`) | 열람 시각, 다시 알림, 전자결재 번호 |
| SCR-13 | `GET /assignments?role=`, `PUT /assignments/{id}` | — | 재요청, 직접 요청, 회신, 내보내기 |
| SCR-16 | `GET /products`, `/products/families`, `/products/{code}`, `/rules/items` | — | 엑셀 가져오기, 내보내기, 요구 조건으로 찾기, 고치기, 제품 카드 자료 |
| SCR-17 | `GET /rules/compare`, `/rules/items`, `/rules/risk-expressions` | — | 수정 요청, 규칙 추가, 수정 이력, 규칙별 판정 목록 (단위 사전은 CR-10으로 만들지 않음) |
| SCR-16-1 | `GET /products/{code}`, `/products?family=`, `/rules/items`, `/rules/compare` | — | 칸별 근거 종류, 옵션, 치수·운송, 규격·인증 표, 현장 조건 보정, 입찰 결과 |
| 그 밖 (예시 화면) | — | — | 화면 전체 |

v4.96에서 더해진 예정 API(요약, 개정 안내, 협조 요청 검색·내보내기)는 `_v4.96_결정.md` 3장에 모았다.
