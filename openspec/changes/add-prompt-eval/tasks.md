# Tasks

## 1. 추적표 "계획됨" (먼저 — 명세서 v3와 이 change를 CI 통과 상태로 올리기 위해)

- [x] 1.1 `frontend/scripts/trace.mjs`: 연결 설정 `planned` 허용, 추적표 FR 줄에 "계획됨: …", 이어진 것이 생기면 오류
- [x] 1.2 `docs/추적_연결.json`: FR-18 `planned: "change add-prompt-eval 진행 중"`, FR-19~22 `planned: "명세서 v3 제안 — change 작성 전"`
- [x] 1.3 도구 테스트 `trace.test.mjs`: Scenario "계획된 FR은 실패하지 않음", "계획됨 표시가 남은 FR"
- [x] 1.4 `npm run trace`, `npm run check:trace` 통과

## 2. 역할별 프롬프트 판 (CR-14 포함)

- [ ] 2.1 `llm/tasks.py`: `PROMPTS` 역할별 판 표, `DOC_ROLES`, 공통 머리말과 구분자 감싸기 함수(`as_document`), 본문 속 구분자 글자 바꾸기
- [ ] 2.2 문서 관련 프롬프트 모두 구분자 사용(분류·구분·유형·위험 설명·검증·초안·협조 질문·도우미 관찰), 근거 대조는 되돌린 글자로
- [ ] 2.3 `pipeline/run.py`: 재사용 열쇠에 `DOC_ROLES` 판만, 실행 기록 `prompt_versions`. 실행 기록 화면·API가 예전 `prompt_version`도 읽음
- [ ] 2.4 `tests/fixtures/prompt_hashes.json`과 "판을 올리세요" 테스트
- [ ] 2.5 테스트: Scenario "한 역할만 바꾸면 그 판만 오름", "문서 처리 역할을 바꾸면 다시 분석", "본문을 구분자로 감쌈", "본문 속 구분자 글자", "AI가 주입을 따라도 판정은 그대로"

## 3. 평가셋

- [ ] 3.1 `pipeline/prompt_eval.py`: 평가셋 JSONL 읽기·검사, 평가셋 판(해시), 역할별 입력·정답 모양 검사
- [ ] 3.2 `rfp-db export-eval-set --key 이름 [--out 경로]`: 기존 유형 정답지를 평가셋으로 (고객 원문 정답지는 `data/private/eval/`로만)
- [ ] 3.3 공개 평가셋 `data/eval/public.jsonl`: 문장 구분 20, 유형 30, 문장 초안 10, 검토 도우미 8, 주입 10쌍. 사람이 확인한 줄만 `HUMAN`
- [ ] 3.4 위험 설명·검증 평가셋 형식과 예시 2줄(`data/eval/README.md`에 사람 표시 방법)
- [ ] 3.5 테스트: Scenario "평가셋 읽기", "형식이 틀린 줄"

## 4. 평가 실행·기록 (마이그레이션 0040)

- [ ] 4.1 마이그레이션 `0040_prompt_eval.sql`: `prompt_eval_run`, `prompt_eval_item`, 기준선 부분 유일 색인
- [ ] 4.2 역할별 채점(label·type·draft·assistant·risk·verify), 정답 출처별 지표와 "근거 약함", 답 없음 처리
- [ ] 4.3 주입 짝 문항 비교와 주입 영향
- [ ] 4.4 검토 도우미 평가용 합성 검토 적재(평가 전용 스키마)와 도구 지표
- [ ] 4.5 반복 실행(최소·최대·평균), 동시 호출, 순서대로 저장
- [ ] 4.6 비용 어림과 상한(`RFP_EVAL_MAX_KRW`, `--yes`), AI 없음이면 "건너뜀"
- [ ] 4.7 기준선 정하기(`--baseline`), 비교와 회귀 판정, 맞음 → 틀림 문항 목록, 평가셋별 문턱(`threshold_pp`)
- [ ] 4.8 `rfp-db eval-prompts --set 이름 [--repeat N] [--baseline] [--yes] [--report 경로] [--write-baseline-file]`
- [ ] 4.9 API `GET /api/prompt-evals?set=`(평가 기록, 모델별 최근), `GET /api/prompt-evals/{id}`(문항 결과), 스키마, `npm run gen:api`
- [ ] 4.10 설정 변수 `RFP_EVAL_MAX_KRW`: `config.py`, `.env.example`, `docker-compose.yml` 세 곳
- [ ] 4.11 테스트(FakeLLM): Scenario "사람 합의 유형 평가셋 평가", "호출 실패 문항", "문장 초안 검사 통과율", "정답 출처가 섞인 평가셋", "점수가 떨어진 새 판", "기준선 없음", "세 번 반복", "주입 영향 없음", "주입 영향 있음", "도우미 도구 사용 평가", "오픈 모델과 나란히", "상한을 넘는 평가", "키 없음"

## 5. CI

- [ ] 5.1 `.github/workflows/prompt-eval.yml`: 경로 거르기, 키 없으면 건너뜀, 작업 요약에 보고서, 기준선 파일과 비교해 회귀면 실패
- [ ] 5.2 `data/eval/baseline.json` 만들기(로컬에서 Gemini로 공개 평가셋 1회, 기준선)
- [ ] 5.3 테스트: Scenario "프롬프트 파일을 바꾼 PR", "프롬프트와 무관한 PR" (워크플로 경로 거르기를 읽어 확인하는 도구 테스트)

## 6. 측정과 문서

- [ ] 6.1 실제 측정 1회: 공개 평가셋을 Gemini 3.8 Flash로 3번 반복, 오픈 모델 1종(`local`, Ollama)으로 1번. 결과를 `docs/05-evaluation.md`에 "프롬프트 평가" 절로
- [ ] 6.2 `docs/03-adr.md`에 ADR-009(평가를 직접 만든 이유와 대안), `docs/02-architecture.md` AI 역할 표에 프롬프트 판·평가 연결
- [ ] 6.3 `docs/06-my-contribution.md`에 "팀 프로젝트 이후 개인 개선" 절, README "한눈에 보기" 성과 칸 갱신
- [ ] 6.4 명세서 FR-18 상태 표시를 [제안] → 구현 완료로, 가안 숫자를 design 값으로

## 7. 마무리

- [ ] 7.1 AGENTS.md 7장 검사 전부(ruff·pytest·lint·check:api·check:trace·build·`openspec validate --all --strict`)
- [ ] 7.2 `npx --yes @fission-ai/openspec@1.14.3 archive add-prompt-eval --yes`, `docs/추적_연결.json`의 FR-18을 `specs: ["prompt-evaluation"]`로, AGENTS.md change 표에 128번 줄(마이그레이션 0040), `npm run trace`
