# Tasks

## 1. 분류

- [x] 1.1 `classify.suggest_bundle`, `classify.apply_choice`, 추천 이유 문구
- [x] 1.2 `process_document`·`execute_run`·`run_to_end`에 `choices`, 사람 값이면 처리 판 구별

## 2. API

- [x] 2.1 `POST /runs/preview`, `POST /runs/library/preview`, 응답 `DocumentPreview`
- [x] 2.2 `POST /runs`(`choices` JSON 칸), `POST /runs/library`(`choices`)
- [x] 2.3 `npm run gen:api`

## 3. 화면

- [x] 3.1 검토 등록 문서 표: 추천 불러오기, 종류·묶음 고르기, 판정 대상·이유, "사람이 바꿈"
- [x] 3.2 SCR-07 명세·공유 갱신

## 4. 테스트 (Scenario마다 하나 이상, 이름에 Scenario 이름)

- [x] 4.1 백엔드: 문서 목록에 있는 문서 추천 / 목록 밖 IEC 문서 추천 / 판정하지 않는 문서 추천 / 묶음 C 문서를 B로 정하고 시작 / 같은 파일을 다른 묶음으로 다시 시작
- [x] 4.2 화면: 올린 문서의 분류 추천 보기 / 묶음을 바꿔 시작 (`e2e/document-confirm.spec.ts`)

## 5. 마무리

- [x] 5.1 ruff, pytest, lint, check:api, build, `openspec validate --all --strict`
- [x] 5.2 archive
