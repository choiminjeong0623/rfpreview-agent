## 1. 백엔드

- [x] 1.1 `send_run` 링크: 지금 작업 토큰 → 가장 최근 AI 호출 토큰 → 빈 토큰 순서로 trace 고르기
- [x] 1.2 `RFP_LANGFUSE_UI_URL`: 검토 trace·데이터셋 링크를 화면 주소로
- [x] 1.3 `RFP_LANGFUSE_SEND_TIMEOUT_S`: `langfuse_ops` 요청 시간 제한, `prompt_source.client(timeout)`
- [x] 1.4 설정 세 곳(config.py·.env.example·docker-compose.yml)에 `RFP_LANGFUSE_TIMEOUT_S` 포함

## 2. 문서·검사

- [x] 2.1 테스트(다시 처리한 작업 링크, 화면 주소, 보내기 시간 제한)
- [x] 2.2 README·ADR-011·setup 안내
- [x] 2.3 검사, archive, AGENTS.md 표, `npm run trace`
