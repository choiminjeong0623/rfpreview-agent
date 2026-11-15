## 1. 백엔드

- [x] 1.1 마이그레이션 0045: `prompt_eval_run.langfuse_url`
- [x] 1.2 `prompt_source.Client`: 데이터셋 조회·만들기, 데이터셋 항목, 점수, 프로젝트 요청
- [x] 1.3 `langfuse_ops`: `push_dataset`(비공개 거절), `record_experiment`(반복마다 실험, 문항마다 trace·점수, 주소)
- [x] 1.4 `rfp-db langfuse-push-dataset --set`, `eval-prompts`·화면 평가 끝에 실험 기록
- [x] 1.5 설정 `RFP_LANGFUSE_RECORD` 세 곳(config·.env.example·docker-compose), `/api/health`에 기록 켬 여부

## 2. API·화면

- [x] 2.1 응답: `PromptEvalRun.langfuse_url`, `PromptVersionEval.langfuse_url`, `PromptEvalJob.langfuse_url`·`langfuse_error`, `npm run gen:api`
- [x] 2.2 프롬프트 관리: 판 기록 평가 칸·화면 평가 결과에 "Langfuse에서 보기"

## 3. 문서·검사

- [x] 3.1 테스트 `tests/test_langfuse_experiments.py`(가짜 Langfuse)
- [x] 3.2 ADR-011·설치 안내·SCR-26 문서
- [x] 3.3 검사, archive, AGENTS.md 표, `npm run trace`
