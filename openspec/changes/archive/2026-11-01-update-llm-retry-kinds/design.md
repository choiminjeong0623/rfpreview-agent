# 설계

- `client.py`: `LLMFormatError(LLMFailure)`, `LLMConfigError(LLMFailure)`. `call_with_retry`는 `generate_json`에서 난 예외와 `validate`에서 난 예외를 나눈다.
  - `generate_json` 안 `json.JSONDecodeError` → 형식 오류. `google.genai.errors.ClientError`이고 code가 400·401·403·404 → 설정 오류(예외 이름으로만 보지 않고 `code` 속성으로 판단해 테스트 대역도 쓸 수 있게). 그 밖(시간 초과, 5xx, 429, 연결) → 재시도.
  - `validate` 실패(어떤 예외든) → 형식 오류, 재시도 없음.
- 요청 수·재시도 수는 지금처럼 센다(형식 오류는 요청 1·재시도 0).
- `_pick_each`: `LLMFormatError`일 때만 나눈다. 다른 실패(재시도 뒤 연결 오류)는 나누지 않고 바로 실패 — 예전에는 시간 초과도 나눠 요청이 늘었다.
- `explain_risk`: `LLMFormatError` → `DroppedExplanation(FORMAT_ERROR)`. 다른 실패는 그대로 올려 검토를 멈춘다(CR-12).
- `draft_sentences`: 묶음 하나가 `LLMFormatError`면 그 묶음 줄 모두 None → 코드 기본 문장.
- 실패 메시지: run.py가 `LLMConfigError`면 그 메시지, 다른 `LLMFailure`면 "처리 실패 — 다시 시도".
- 위험: Gemini가 temperature 0에서도 가끔 다른 답을 낼 수 있어, 한 번 더 물었으면 맞았을 형식 오류를 잃을 수 있다. 묶음은 나눠 묻고 설명·초안은 코드가 대신하므로 결과가 비지는 않는다.
