# Proposal: 여러 회사 모델 비교 평가 (add-model-compare)

## Why

- 멘토 피드백 "프롬프트에 따라 품질을 측정하는가"에 FR-18(add-prompt-eval)이 프롬프트 판으로 답했다.
  남은 질문은 "그 모델을 고른 근거가 있는가"다.
- 지금 평가는 AI 사용 방식 `gemini`·`local` 가운데 서버에 설정된 하나로만 돈다. 방식을 바꾸려면 설정을 바꿔
  다시 돌려야 하고, Claude·GPT는 잴 수 없으며, 결과에 응답 시간이 없다.
- 그래서 "같은 품질을 더 싸게" 또는 "외부 전송이 막히면 품질이 얼마나 떨어지나"에 숫자로 답하지 못한다.
- 명세서 v4 FR-23 (11-15 제안, 민정 진행 확인).

## What Changes

- 비교할 모델을 `공급자:모델` 목록으로 받는다. 공급자는 `gemini`·`anthropic`·`openai`·`local`.
  키는 환경 변수로만 받는다(`GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `RFP_LOCAL_LLM_*`).
- `llm/client.py`: Anthropic 클라이언트(공식 SDK, 구조화 출력), OpenAI는 이미 있는 OpenAI 호환 클라이언트를
  OpenAI 주소로 쓴다. 모두 같은 `generate_json`, 같은 오류 종류(CR-12), 같은 호출 기록(FR-21).
- `rfp-db eval-prompts --set 이름 --models a,b,c`: 같은 평가셋·같은 프롬프트 판을 모델마다 돌려
  비교 묶음 하나로 저장하고 비교표를 낸다. 역할별 주 지표, 형식 오류율, 주입 영향, 호출·토큰, 추정 비용,
  문항 응답 시간 p50·p95.
- "같은 품질에 가장 싼 모델" 한 줄(코드가 고름).
- 비용 상한은 모델 합계 어림으로 시작 전에 본다. 단가 표에 Claude 모델(팀 가정)과 설정 `RFP_EVAL_PRICES`.
- 고객 원문 평가셋(`data/private/`)은 운영진이 허용한 Gemini와 `local`로만 보낸다.
- 마이그레이션 0044: 평가 실행에 비교 묶음 번호·공급자·응답 시간 칸. 평가 조회 API 응답에 같은 칸.

## Non-Goals

- 분석 운영 모델 바꾸기. `RFP_AI_MODE`는 그대로다. 비교는 평가 전용이다.
- 요청마다 모델을 고르는 라우터, 실패하면 다른 회사로 넘기기.
- 모델마다 다른 프롬프트. 같은 판을 그대로 보낸다(비교 조건을 같게).
- AI 채점자. 코드로 잴 수 있는 지표만(FR-18 ④).
- 비교 결과 화면. 이번에는 명령 출력(마크다운)과 API 조회까지만 한다.
- 비전 모델 비교(다음 change, FR-24).
- 실제 비교 실행 결과(키 등록 뒤 사람이 로컬에서 돌림). CI는 지금처럼 Gemini 하나만.

## Capabilities

- MODIFIED `prompt-evaluation`: 모델 비교를 여러 공급자·한 번 실행으로, 응답 시간, 가장 싼 모델, 외부 전송 거절.

## Impact

- 코드: `llm/client.py`, `pipeline/prompt_eval.py`, `pipeline/run_log.py`(단가), `db/cli.py`, `config.py`,
  `api/schemas.py`(+ `openapi.json`·`api.gen.ts`).
- 의존성: `anthropic`(`uv add`). OpenAI는 새 의존성 없이 httpx.
- 설정: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `RFP_EVAL_PRICES` — `config.py`·`.env.example`·`docker-compose.yml`.
- DB: `0044_model_compare.sql`.
