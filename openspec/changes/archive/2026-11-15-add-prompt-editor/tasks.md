## 1. 백엔드

- [x] 1.1 `pipeline/prompt_editor.py`: 역할 상세(코드 틀·운영·staging 판·검사), staging 저장(검사·권한), 화면 평가 작업(그 역할 문항, 반복 3, 기준선 비교), 운영으로 올리기(승인자, 평가한 판 확인)
- [x] 1.2 API `/api/prompts/{role}`·`drafts`·`evaluations`·`evaluations/latest`·`promote`, 응답 스키마, `npm run gen:api`

## 2. 화면

- [x] 2.1 프롬프트 관리(SCR-26) 줄 → 오른쪽 패널: 판 기록, 글 고치기, 자리표시자·규칙 표시, 바꾼 이유
- [x] 2.2 [평가 돌리기]·평가 결과 상자(지표·기준선·회귀), [운영으로 올리기], 잠김 이유(Langfuse 없음·AI 끔·권한)

## 3. 문서·검사

- [x] 3.1 테스트 `tests/test_prompt_editor.py`(가짜 Langfuse, 가짜 AI)
- [x] 3.2 SCR-26 문서, ADR-011·설치 안내
- [x] 3.3 검사, archive, AGENTS.md 표, `npm run trace`
