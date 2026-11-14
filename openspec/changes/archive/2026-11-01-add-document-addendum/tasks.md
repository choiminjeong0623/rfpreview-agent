# Tasks

## 1. 문서

- [x] 1.1 명세서 FR-01 ⑤⑥, FR-10 ⑤, 기획서 부록 B
- [x] 1.2 SCR-08 화면 정의서·`SCR-08_공유.md`·`SCR-08-5_공유.md`(문서 추가는 범위 밖 → 만듦)

## 2. 처리 흐름

- [x] 2.1 `db/migrations/0021_document_addendum.sql`: 이력 동작 값 ADD
- [x] 2.2 `pipeline/doc_add.py`: 문서 추가 준비(단계·역할·같은 파일 검사, 이력), 판정 이어받기, 위험 조건 바꾸기
- [x] 2.3 `pipeline/run.py`: 판정 단계 앞뒤 이어받기, 위험 조건 새로 만든 뒤 바꾸기, 같은 위험 조건은 AI 설명 다시 씀

## 3. API

- [x] 3.1 `POST /api/runs/{id}/documents` (multipart files, choices, actor_id)
- [x] 3.2 `npm run gen:api`
- [x] 3.3 테스트: Scenario마다 (`tests/test_document_addendum.py`)

## 4. 화면

- [x] 4.1 "문서 n개" 창 "문서 추가": 파일 고르기, 분류 추천, 묶음·종류 고르기, "추가하고 다시 분석" (엔지니어·담당자 확인 단계만)
- [x] 4.2 이력 탭 "문서 추가: 파일 이름"
- [x] 4.3 e2e: 문서 추가 뒤 확정 줄 그대로
