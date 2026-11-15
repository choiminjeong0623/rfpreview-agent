## Why

add-langfuse-trace-push를 실제 self-host Langfuse(docker 백엔드)로 확인하니 세 가지가 맞지 않았다.

- 단계부터 다시·문서 추가·다시 시도처럼 AI를 다시 부르지 않은 작업이 끝나면, 링크가 그 작업의 실행 토큰으로 만든 빈 trace를 가리켰다. AI 호출은 처음 작업 토큰에 붙어 있다.
- docker 백엔드는 Langfuse에 `http://host.docker.internal:3000`으로 닿는데, 같은 주소로 만든 링크는 브라우저에서 열리지 않았다.
- Langfuse 요청 시간 제한(`RFP_LANGFUSE_TIMEOUT_S`, 5초)은 분석 시작 때 프롬프트를 가져오는 용도인데, 기록 보내기에도 같이 쓰여 Langfuse가 조금만 느려도 "timed out"으로 끝났다. 이 설정은 docker-compose.yml·.env.example에도 없어 docker 백엔드에서 바꿀 수 없었다.

## What Changes

- 검토 작업 끝 자동 전송의 링크는 그 검토에서 가장 최근에 AI를 부른 실행의 trace를 가리킨다(지금 작업이 AI를 불렀으면 그 작업).
- 새 설정 `RFP_LANGFUSE_UI_URL`(화면 링크용 Langfuse 주소, 비면 `LANGFUSE_HOST`). 검토 trace·평가 실험(데이터셋) 링크 모두 이 주소로 만든다.
- 새 설정 `RFP_LANGFUSE_SEND_TIMEOUT_S`(기본 30초): 데이터셋·실험·호출 기록 보내기, 프롬프트 올리기·운영 승격 명령의 요청 시간 제한. 프롬프트 가져오기·편집 화면은 `RFP_LANGFUSE_TIMEOUT_S`(5초) 그대로.
- 세 설정(`RFP_LANGFUSE_TIMEOUT_S` 포함)을 config.py·.env.example·docker-compose.yml에 함께.

## Capabilities

### Modified Capabilities

- `prompt-evaluation`: "Langfuse로 호출 기록 보내기"의 링크 대상과 링크 주소.

## Impact

- 백엔드 `pipeline/langfuse_ops.py`, `llm/prompt_source.py`(`client(timeout)`), `config.py`. 마이그레이션 없음, API 모양 그대로.
- 관련: FR-18·FR-21, ADR-011.
