# 설계: add-ai-mode

## 결정

- **설정 위치**: `config.Settings`에 `rfp_ai_mode`(gemini|local|off, 기본 gemini), `rfp_local_llm_url`, `rfp_local_llm_model`, `rfp_local_llm_key`, `rfp_local_embed_model`. `make_llm(settings)`가 방식에 따라 `GeminiLLM`·`LocalLLM`·None을 만든다. 언어 모델 호출은 여전히 `llm/client.py` 한 곳(AGENTS.md 6장).
- **사내 모델은 OpenAI 호환 API**: vLLM·Ollama·LM Studio·사내 게이트웨이가 모두 `/v1/chat/completions`·`/v1/embeddings`를 준다. 새 의존성 없이 이미 있는 `httpx`로 부른다. JSON 답은 `response_format: json_schema`(우리 스키마가 이미 소문자 JSON Schema), temperature 0(CR-11).
- **오류 종류**: HTTP 상태 코드를 예외 `code`로 실어 B6의 `_is_config_error`(400·401·403·404)를 그대로 쓴다. 429·5xx·연결·시간 초과는 재시도. 답이 JSON이 아니면 형식 오류(다시 묻지 않음).
- **벡터 모델 이름**: 벡터는 `(model, text_hash)`로 저장되므로 사내 벡터 모델 이름을 `embed_model`로 둔다. 화면에서 지난 확정을 찾을 때도 지금 설정의 벡터 모델로 찾는다(`meaning.current_model()`).
- **처리 판**: 실행의 code_version에 모델 이름이 들어가므로 방식을 바꾸면 같은 파일도 새로 분석된다(문서 재사용은 같은 판끼리만).
- **비용**: 사내 모델은 단가표에 없어 실행 기록 추정 비용이 비어 "단가 없음"으로 보인다(기존 규칙).
- **화면**: 목업에 없는 한 줄 안내. 검토 등록 화면 시작 단추 근처와 실행 기록 머리 줄. `docs/screens/SCR-25_공유.md`에 적는다.

## 대안

- LiteLLM 같은 여러 모델 라이브러리: 의존성이 크고 판 고정이 어렵다. OpenAI 호환 하나로 대부분의 사내 서버를 덮는다.
- 화면에서 방식 바꾸기: 운영 보안 설정을 일반 사용자가 바꾸면 안 된다. 환경 변수만.

## 위험

- 사내 모델의 JSON 스키마 지원이 서버마다 다르다 → 형식 오류는 B6 규칙대로 묶음 나누기·코드 문장으로 흡수. 실제 사내 서버로는 시험하지 못함 [확인 필요].
