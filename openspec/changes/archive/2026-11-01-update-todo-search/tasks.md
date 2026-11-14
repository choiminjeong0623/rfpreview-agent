## 1. 백엔드

- [x] 1.1 `GET /assignments` role 생략 시 세 부서, `assignments_for` 여러 부서
- [x] 1.2 보내기 `resend`(메일 보냄 요청 다시 보내기, 이력)
- [x] 1.3 `POST /assignments/export` + `pipeline/assignment_export.py`
- [x] 1.4 백엔드 테스트 `tests/test_todo_search.py` (Scenario마다)

## 2. 화면 (SCR-13 v4.96)

- [x] 2.1 `npm run gen:api`, `api.ts`(assignments role 생략, exportAssignments, sendRequests resend)
- [x] 2.2 `mockup/TodoV496.css`, `Pager` 쪽 크기 목록
- [x] 2.3 `views/Todo.tsx`: 탭 건수, 검색 영역·칩, 요약 줄 거르기, 회신 표시, 담당별·RFP별, 재요청, 내보내기
- [x] 2.4 e2e `todo-search.spec.ts`(Scenario마다), 예전 `todo.spec.ts` 고침

## 3. 마무리

- [x] 3.1 SCR-13 "구현됨", `SCR-13_공유.md`, AGENTS.md 표
- [x] 3.2 검사 통과, archive
