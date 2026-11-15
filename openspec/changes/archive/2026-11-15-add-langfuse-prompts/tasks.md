## 1. 프롬프트 틀

- [x] 1.1 `tasks.TEMPLATES`: 역할 8개 프롬프트를 `{{이름}}` 틀로, 보내는 글은 그대로(해시 같음)
- [x] 1.2 `llm/prompt_source.py`: 끄면 코드 판, 켜면 Langfuse 판 가져오기·검사·코드 판으로 돌아가기, 캐시, 실행 판 묶음(`use`)

## 2. 실행·기록

- [x] 2.1 `execute_run`: 시작할 때 판 묶음을 골라 실행 기록(`prompt_versions`·`prompt_sources`)과 재사용 열쇠에, AI 호출 기록에 실제 판
- [x] 2.2 `rfp-db langfuse-push-prompts`, `eval-prompts --promote`, `langfuse-push-traces`(`pipeline/langfuse_ops.py`)
- [x] 2.3 OTLP 내보내기에 Langfuse 프롬프트 이름·버전 속성

## 3. 화면·설정

- [x] 3.1 `/api/health` `prompt_source`·`prompt_label`, `/api/prompts` 역할마다 가져온 곳과 `langfuse`, `npm run gen:api`
- [x] 3.2 프롬프트 관리 화면(SCR-26): 가져온 곳 칸, Langfuse 요약 칸, 안내 문구
- [x] 3.3 설정 `RFP_LANGFUSE`·`RFP_LANGFUSE_LABEL`·`LANGFUSE_*` 세 곳(config·.env.example·docker-compose)

## 4. 문서·검사

- [x] 4.1 테스트 `tests/test_langfuse_prompts.py`(가짜 Langfuse)
- [x] 4.2 ADR-010 고침(구현함), 설치 안내, SCR-26 문서
- [x] 4.3 검사, archive, AGENTS.md 표, `npm run trace`
