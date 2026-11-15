## 1. 조회

- [x] 1.1 `pipeline/prompt_registry.py`: 실행 기록·AI 호출·평가 기록에서 역할별 판 기록과 점수 모으기
- [x] 1.2 `api/prompts.py` `GET /api/prompts`, 응답 모양 `PromptOverview`, `npm run gen:api`
- [x] 1.3 테스트 `tests/test_prompt_view.py`: Scenario 2개

## 2. 화면

- [x] 2.1 `views/Prompts.tsx`(SCR-26): 요약 칸, 역할 표, 줄을 누르면 판 기록
- [x] 2.2 메뉴 시스템 관리 > 프롬프트 관리(`#/prompts`), 현재 위치
- [x] 2.3 문서: `docs/screens/SCR-26_공유.md`, 화면 목록, SCR-00 메뉴 표

## 3. 설계 메모

- [x] 3.1 `docs/03-adr.md` ADR-010: 화면은 보기 전용, 편집·배포는 다음 단계 Langfuse(label 배포, 평가 통과 뒤 승격, 연결 실패 시 코드 판, self-host)

## 4. 마무리

- [x] 4.1 검사(ruff·pytest·lint·check:api·check:trace·build·openspec validate)
- [x] 4.2 archive, AGENTS.md 표, `npm run trace`
