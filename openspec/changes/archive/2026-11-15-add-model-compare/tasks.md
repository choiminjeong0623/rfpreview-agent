# Tasks

## 1. 명세서·추적

- [x] 1.1 명세서 v4 제안(FR-23~26, NFR-15·16, 9장 데이터) — `docs/reference/기능요구사항명세서_v1.md`
- [x] 1.2 `docs/추적_연결.json`: FR-23 → `prompt-evaluation`, FR-24~26 `planned`

## 2. 공급자 클라이언트

- [x] 2.1 `llm/client.py`: `strict_schema`, `AnthropicLLM`(공식 SDK, 구조화 출력, SDK 재시도 끔, 오류 → `HTTPStatusFailure`), `LocalLLM(temperature=None)`
- [x] 2.2 `ModelSpec`·`parse_models`·`make_compare_llm`(공급자 → 클라이언트, 키 없음·외부 전송 거절 이유)
- [x] 2.3 `config.py`·`.env.example`·`docker-compose.yml`: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `RFP_EVAL_PRICES`; `uv add anthropic`
- [x] 2.4 테스트: Anthropic 가짜 응답(JSON·거절·429·401), OpenAI temperature 빠짐, 모델 목록 나누기

## 3. 비교 평가

- [x] 3.1 `Answer.ms`, `EvalResult` p50·p95(nearest-rank), 공급자·비교 묶음
- [x] 3.2 `run_log`: Claude 단가(팀 가정), `RFP_EVAL_PRICES` 읽기
- [x] 3.3 `prompt_eval.compare_models`: 키 없음·외부 전송 거절 건너뜀, 합계 상한, 모델마다 평가
- [x] 3.4 `cheapest` 고르기, `compare_report` 마크다운 표
- [x] 3.5 마이그레이션 `0044_model_compare.sql`, `save`·`runs`에 새 칸, API 스키마, `npm run gen:api`
- [x] 3.6 `rfp-db eval-prompts --models`(`--baseline`과 함께 못 씀)
- [x] 3.7 테스트: Scenario "키가 없는 모델이 섞인 비교", "한 모델의 설정 오류", "비교 기록 묶음", "응답 시간 기록", "싸고 품질이 같은 모델", "단가를 모르는 모델", "비공개 평가셋과 외부 모델", "합계가 상한을 넘는 비교"

## 4. 마무리

- [x] 4.1 `data/eval/README.md`에 비교 실행 방법
- [x] 4.2 검사(ruff, pytest, 프런트 lint·check:api·check:trace·build, openspec validate)
- [x] 4.3 archive, AGENTS.md 표 132번(0044), `npm run trace`
