# Design: 여러 회사 모델 비교 평가 (add-model-compare)

## 1. 모델 지정

- `--models`는 쉼표로 나눈 `공급자:모델`. 첫 `:`에서만 나눈다(`local:qwen2.5:7b`의 모델은 `qwen2.5:7b`).
- 공급자 → 클라이언트와 키:

  | 공급자 | 클라이언트 | 키·주소 | 외부 전송 |
  |---|---|---|---|
  | `gemini` | `GeminiLLM` | `GEMINI_API_KEY` | 외부 (운영진 허용, NFR-07 Q6) |
  | `anthropic` | `AnthropicLLM` (새) | `ANTHROPIC_API_KEY` | 외부 (허용 안 됨) |
  | `openai` | `LocalLLM`을 `https://api.openai.com/v1`로 | `OPENAI_API_KEY` | 외부 (허용 안 됨) |
  | `local` | `LocalLLM` | `RFP_LOCAL_LLM_URL`(+ `RFP_LOCAL_LLM_KEY`) | 내부 |

- 키(local은 주소)가 없으면 그 모델은 `SKIPPED`, 이유 "키 없음".
- 평가셋 파일이 `data/private/` 아래면 `anthropic`·`openai`는 `SKIPPED`, 이유 "외부 전송 허용 안 됨"(요청 0건).

## 2. Anthropic 클라이언트

- 공식 SDK `anthropic.Anthropic(api_key, timeout, max_retries=0)`. SDK 재시도를 끄고 재시도는 `call_with_retry`가
  CR-12대로 한다(호출 기록·재시도 수가 다른 공급자와 같게).
- `messages.create(model, max_tokens=16000, messages=[user], output_config={"format": {"type": "json_schema",
  "schema": …}})`. `temperature`는 보내지 않는다(최신 모델은 400). 생각(thinking)·effort는 모델 기본값 그대로
  — 공급자마다 "기본 설정의 모델"을 비교한다.
- 구조화 출력은 모든 object에 `additionalProperties: false`가 필요해 `strict_schema()`가 복사본에 더한다.
- 답: 첫 `text` 블록을 `json.loads`. 거절(`stop_reason: refusal`)이나 빈 답은 JSON이 아니므로 형식 오류(다시 묻지 않음).
- 오류: SDK `APIStatusError`는 `HTTPStatusFailure(status_code)`로 바꿔 올린다. 400·401·403·404는 설정 오류,
  429·5xx·연결·시간 초과는 재시도(기존 `_is_config_error` 그대로).
- 토큰: `usage.input_tokens`, `usage.output_tokens`(생각 토큰은 출력에 포함되어 따로 없음).

## 3. OpenAI

- `LocalLLM(base_url="https://api.openai.com/v1", model, api_key)`. `temperature`는 보내지 않는다
  (`LocalLLM(temperature=None)`): 일부 최신 모델이 0을 받지 않는다. 사내 `local`은 지금처럼 0.
- `response_format: json_schema`(strict 아님) 그대로.

## 4. 응답 시간

- 문항 하나를 묻는 데 걸린 시간(재시도 포함, 검토 도우미는 도구 반복 전체)을 `Answer.ms`로 잰다.
- 평가 실행의 p50·p95는 모든 반복·모든 문항의 `ms`에서 최근접 순위(nearest-rank)로. 답 없음 문항도 넣는다
  (기다린 시간은 같다). 동시에 묻는 개수는 모델마다 같게(`RFP_LLM_WORKERS`).

## 5. 비용

- 단가 표(`run_log.PRICES_USD_PER_M`, 팀 가정)에 Claude Opus 5.5 · Sonnet 5.5 · Haiku 5.5를 더한다(2026-11 공개 단가).
- `RFP_EVAL_PRICES="모델=입력/출력;…"`(1M 토큰당 달러, 팀 가정)로 표에 없는 모델(GPT·오픈 모델) 단가를 준다.
  `local`의 단가를 주지 않으면 "단가 모름".
- 상한: 키가 있고 보낼 수 있는 모델들의 어림 비용 합. 단가 모르는 모델은 합에서 빼고 보고서에 경고.
  합이 상한을 넘으면 `--yes` 없이는 아무 모델도 시작하지 않는다.

## 6. 같은 품질에 가장 싼 모델

- 후보: 상태 DONE, 주입 영향 0, 추정 비용을 아는 모델.
- 역할마다 주 지표 = `METRICS[role]`의 첫 지표, 값 = 기준 출처의 최솟값. 그 역할의 최고 값(모든 DONE 모델 중)보다
  `threshold_pp` 넘게 낮으면 탈락. 모든 역할을 통과한 후보 중 비용이 가장 적은 모델(같으면 p95가 작은 쪽, 다음 이름순).
- 없으면 "고를 수 없음(이유)". 코드만(CR-01).

## 7. 저장 (0044)

```sql
ALTER TABLE prompt_eval_run ADD COLUMN compare_id INT;          -- 같은 --models 실행이면 같은 번호
ALTER TABLE prompt_eval_run ADD COLUMN provider VARCHAR(20);    -- gemini / anthropic / openai / local
ALTER TABLE prompt_eval_run ADD COLUMN latency_p50_ms INT;
ALTER TABLE prompt_eval_run ADD COLUMN latency_p95_ms INT;
CREATE SEQUENCE prompt_eval_compare_seq;
```

- `ai_mode` 칸에는 공급자를 대문자로(`ANTHROPIC`·`OPENAI` 등, 10자 안). 예전 기록은 `provider`가 비어 있다.
- 비교 실행은 기준선을 만들지 않는다(`--models`와 `--baseline`은 함께 쓸 수 없음). 기준선은 지금처럼 한 모델로.
- 비교 실행에서도 모델별로 FR-18 기준선과 비교하지 않는다(기준선은 모델 하나의 회귀용). 종료 코드는 0.

## 8. 버린 대안

- **LiteLLM 같은 통합 라이브러리**: 공급자마다 구조화 출력·오류 코드 처리가 숨겨져 CR-12 오류 종류 구분을
  우리가 보장하기 어렵고, 의존성이 크다. 공급자 4개면 직접 두는 편이 짧다.
- **OpenAI 공식 SDK**: 이미 있는 OpenAI 호환 httpx 클라이언트로 충분하다(사내 `local`과 같은 코드 경로).
- **OpenAI 호환 주소로 Claude 부르기**: Anthropic 공식 SDK의 구조화 출력·오류 형식을 쓰는 쪽이 정확하다.
- **모델마다 프롬프트 다듬기**: 비교 조건이 달라져 "모델 차이"와 "프롬프트 차이"를 가를 수 없다.
