# Proposal

## Why

프롬프트 평가(add-prompt-eval)는 결과를 우리 DB와 보고서로만 남겨, 프롬프트 판·모델마다 문항 단위 결과를 나란히 보려면 보고서 여러 개를 맞대어야 한다. Langfuse 연동(add-langfuse-prompts)으로 프롬프트 판은 이미 Langfuse에 있으니, 평가셋과 평가 결과도 같은 곳(Datasets·Experiment)에 두면 "이 판이 어느 문항에서 좋아지고 나빠졌는지"를 판 기록 옆에서 본다. 사용자가 계획(11-15) 가운데 1번(Datasets·Experiment)부터 하기로 했다. 3번(분석 뒤 호출 기록 자동 전송)은 이 change가 끝난 뒤 따로 한다.

관련: FR-18·NFR-13(add-prompt-eval), FR-21(add-ai-call-trace), ADR-011(add-langfuse-prompts), add-prompt-editor, SCR-26 프롬프트 관리.

## What Changes

- `rfp-db langfuse-push-dataset --set 이름`: 평가셋 문항을 Langfuse 데이터셋 `rfp-eval-<평가셋>`의 항목(입력·기대 답·역할·정답 출처)으로 올린다. 항목 번호를 문항 번호로 고정해 다시 올려도 늘지 않는다. `data/private/` 평가셋은 거절한다.
- `RFP_LANGFUSE_RECORD=on`(기본 off)이면 `eval-prompts`와 프롬프트 관리 화면 평가가 끝날 때 평가를 Langfuse 실험으로 남긴다: 반복마다 실험(experiment) 하나, 문항마다 trace 하나(모델의 답, Langfuse 판이면 프롬프트 버전 연결)와 점수 `ok`(맞음 1·틀림 0, 답 없음은 점수 없음). 판단·회귀는 지금처럼 코드가 한다(CR-01). 실패해도 평가 기록은 남고 이유만 알린다. 비공개 평가셋은 보내지 않는다.
- 평가 기록에 Langfuse 데이터셋 주소를 남기고 프롬프트 관리 판 기록의 평가 칸과 화면 평가 결과에 "Langfuse에서 보기" 링크.
- 마이그레이션 0045: `prompt_eval_run.langfuse_url`.

## Non-Goals

- 사람 확정·수정을 Langfuse 점수로 보내기(계획 2번, 하지 않기로 함).
- Langfuse 관리형 평가자(LLM-as-judge)·Annotation queue(계획 4·5번).
- 정답지 CSV(합성 RFP)를 데이터셋으로 올리기. 이번에는 프롬프트 평가셋만.
- 분석 호출 기록 자동 전송(계획 3번, 다음 change).
