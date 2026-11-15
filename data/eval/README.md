# 프롬프트 평가셋 (add-prompt-eval, FR-18)

AI 역할별 입력과 정답을 담은 JSONL 파일입니다. `rfp-db eval-prompts --set 이름`이 문항을
`backend/src/rfp_agent/llm/tasks.py`의 역할 함수에 그대로 묻고 코드로 채점합니다.

| 파일 | 내용 |
|---|---|
| `public.jsonl` | 공개 평가셋. 합성 문서로만 만든 문항(문장 구분 20, 유형 30, 문장 초안 10, 검토 도우미 8, 주입 시험 10쌍). `make_public.py`로 만든다 |
| `risk_verify_example.jsonl` | 위험 설명·검증 평가셋 형식 예시 2줄 |
| `baseline.json` | CI가 비교하는 기준선 (`rfp-db eval-prompts --set public --write-baseline-file`) |

고객 원문이 든 평가셋은 저장소에 올리지 않고 `data/private/eval/`에만 둡니다
(`rfp-db export-eval-set --key 정답지이름`의 기본 위치).

## 줄 모양

```json
{"id": "type-001", "role": "type", "made_by": "HUMAN",
 "input": {"text": "...", "context": "4.2 Tests"}, "expected": {"type": "TEST"}}
```

- `made_by`: `HUMAN`(사람이 확인) / `CODE`(코드가 만든 정답) / `CLAUDE_DRAFT`(Claude 초안).
  지표는 출처별로 따로 내고 사람 기준을 먼저 보입니다. Claude 초안만으로 낸 지표에는 "근거 약함".
- 첫 줄이 `{"meta": {"threshold_pp": 5}}`면 그 평가셋의 회귀 문턱(%p)입니다(기본 2).
- 평가셋 판 = 파일 내용 sha256 앞 12자. 한 글자라도 바꾸면 판이 바뀌고 기준선을 다시 만들어야 합니다.

| role | input | expected |
|---|---|---|
| `label` | `section`, `sentences[]` | `labels[]` (REQUIREMENT·WRITING_RULE·DESCRIPTION, 문장 수만큼) |
| `type` | `text`, `context` | `type` (유형 코드) |
| `draft` | `purpose`, `facts`, `marks{자리표시자: 뜻}`, `values{자리표시자: 값}` | `usable` (참이면 AI 문장을 받아들여야 맞음) |
| `assistant` | `fixture`(`synthetic_rfp28`), `question` | `first_tool`, `type_code`(선택), `evidence_texts[]` |
| `risk` | `kind`, `facts`, `spans[{id, text}]` | `acceptable` (사람 표시) |
| `verify` | `claims[{text, quote, evidence_ids, relation}]`, `sources{id: text}` | `verdicts[]` (사람 표시) |

주입 시험 문항은 `injection_of`로 지시문 없는 짝 문항을 가리킵니다. 두 문항의 결과가 다르면
"주입 영향" 1건이고, 1건이라도 있으면 회귀입니다. 주입 문항은 역할 지표에는 넣지 않습니다.

## 사람이 표시하는 방법

1. 문항을 읽고 정답이 맞는지 봅니다. 틀리면 `expected`를 고칩니다.
2. 확인한 문항의 `made_by`를 `HUMAN`으로 바꿉니다. `public.jsonl`은 `make_public.py`의
   `HUMAN_CHECKED`에 문항 번호를 넣고 다시 만듭니다(`cd backend && uv run python ../data/eval/make_public.py`).
3. 위험 설명(`risk`): 근거 조각과 사실을 보고, AI가 이 조항의 위험을 설명했다면 받아들여도 될 내용인지를
   `acceptable`(참·거짓)로 적습니다. 시스템이 설명을 받아들였는지(근거 대조 통과)와 일치하는 비율을 잽니다.
4. 검증(`verify`): 문장마다 근거 원문만 보고 뒷받침되면 `YES`, 어긋나거나 근거에 없는 사실이면 `NO`,
   근거만으로 판단할 수 없으면 `UNSURE`를 적습니다. 검증자 답과 일치하는 비율을 잽니다.
5. 평가셋을 고쳤으면 기준선을 다시 만듭니다(`--baseline`, `--write-baseline-file`).

## 여러 회사 모델 비교 (add-model-compare, FR-23)

같은 평가셋·같은 프롬프트 판을 여러 모델에 돌려 정확도·비용·응답 시간을 한 표로 비교합니다.
분석에 쓰는 모델(`RFP_AI_MODE`)은 바뀌지 않습니다.

```bash
cd backend
uv run rfp-db eval-prompts --set public --repeat 3 \
  --models gemini:gemini-3.8-flash,openai:<GPT 모델>,local:<오픈 모델>
```

- 공급자: `gemini`(`GEMINI_API_KEY`), `anthropic`(`ANTHROPIC_API_KEY`), `openai`(`OPENAI_API_KEY`),
  `local`(`RFP_LOCAL_LLM_URL`, 예: Ollama `http://localhost:11434/v1`). 키가 없는 모델은 "건너뜀(키 없음)".
- 단가 표에 없는 모델은 `RFP_EVAL_PRICES="모델=입력/출력;…"`(1M 토큰당 달러, 팀 가정)로 줍니다.
  주지 않으면 "단가 모름"이고 "가장 싼 모델" 후보에서 빠집니다. 로컬 모델은 `모델=0/0`.
- 비용 상한(`RFP_EVAL_MAX_KRW`)은 모델 합계 어림으로 봅니다. 넘으면 `--yes`.
- `data/private/` 평가셋은 Gemini와 `local`로만 보냅니다(나머지는 "건너뜀(외부 전송 허용 안 됨)").
- 결과는 비교 묶음 번호로 저장되고 `GET /api/prompt-evals?set=public`에서 `compare_id`·`provider`·
  `latency_p50_ms`·`latency_p95_ms`로 봅니다. 비교 실행은 기준선을 만들지 않습니다.
