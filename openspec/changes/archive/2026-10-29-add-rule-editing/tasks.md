# Tasks

## 1. 저장

- [x] 1.1 마이그레이션 `0013_rule_edit.sql`
- [x] 1.2 적재가 CSV에서 사라진 비교 방향·위험 표현 줄을 끄게 (`db/seed.py`), 사전 읽기·판정·목록이 꺼진 줄을 빼게
- [x] 1.3 사전별 추가·수정·삭제와 이력 (`pipeline/rule_edit.py`)
- [x] 1.4 다시 적재 때 고침 다시 적용, `--reset-edits`
- [x] 1.5 사전 판에 고침 반영 (`dict_version`, `make_context`)

## 2. API

- [x] 2.1 `POST/PUT/DELETE /api/rules/{dictionary}`, `GET /api/rules/edits`, 권한·검사 오류 문구
- [x] 2.2 `npm run gen:api`

## 3. 화면

- [x] 3.1 판정 규칙 화면: 규칙 추가, 수정·삭제, 입력 창, 마지막 수정, 수정 이력, 역할별 잠금
- [x] 3.2 SCR-17 명세·공유 갱신

## 4. 테스트 (Scenario마다 하나 이상, 이름에 Scenario 이름)

- [x] 4.1 백엔드: reference-data Scenario 10개
- [x] 4.2 화면: review-workspace 새 Scenario 4개 (`e2e/reference.spec.ts`)

## 5. 마무리

- [x] 5.1 ruff, pytest, lint, check:api, build, `openspec validate --all --strict`
- [x] 5.2 archive
