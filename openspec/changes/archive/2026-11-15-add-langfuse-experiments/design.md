# Design

## 결정

1. **판단은 우리 코드, Langfuse는 보기·비교.** 정답 여부·지표·회귀는 지금처럼 `prompt_eval`이 정하고(CR-01), Langfuse에는 그 결과를 문항별 점수 `ok`로 옮겨 적기만 한다. Langfuse 쪽 평가자(LLM-as-judge)는 쓰지 않는다.
2. **실험은 OpenTelemetry 속성으로.** Langfuse 문서는 예전 `POST /api/public/dataset-run-items`를 더 쓰지 말라고 하고(deprecated), 실험을 OTel span 속성으로 잇는 방식을 권한다. 이미 쓰는 `/api/public/otel/v1/traces`로 문항마다 trace 하나(뿌리 span 하나)를 보내고 `langfuse.experiment.id`·`name`·`dataset.id`·`langfuse.experiment.item.id`·`item.root_observation_id`(= 그 span id)·`item.expected_output`, `langfuse.observation.input`·`output`을 붙인다. Langfuse 판으로 물은 문항은 `langfuse.observation.prompt.name`·`version`.
3. **id를 정해진 식으로.** 데이터셋 항목 id = `<평가셋>-<문항 번호>`(Langfuse 항목 id는 프로젝트 안에서 하나라 평가셋 이름을 붙임), trace id = sha256(`eval-<평가 번호>-<반복>-<문항>`) 앞 32자, span id = 같은 식 앞 16자, 점수 id = `<trace id>-ok`. 같은 평가를 다시 보내도 trace·항목이 늘지 않는다.
4. **반복 하나 = 실험 하나.** 실험 id·이름 `eval-<평가 번호>-r<반복>`, 메타데이터에 평가 번호·모델·평가셋 판·프롬프트 판. 데이터셋 화면에서 실험끼리 문항 단위로 비교한다. 평가 기록에는 데이터셋 화면 주소를 남긴다(반복이 여럿이라 실험 하나가 아니라 데이터셋).
5. **점수는 `POST /api/public/scores`.** 문항 trace의 뿌리 span에 `ok`(NUMERIC 1·0), 답 없음은 점수를 보내지 않고 trace 메타데이터에 오류 종류만.
6. **비공개 평가셋은 보내지 않는다.** 공개 평가셋은 합성·공개 자료라 입력·답을 보내도 되고, `data/private/`는 데이터셋·실험 모두 보내지 않는다(add-model-compare의 외부 전송 규칙과 같음).
7. **설정 `RFP_LANGFUSE_RECORD`.** 프롬프트를 가져오는 `RFP_LANGFUSE`와 따로라, 코드 판을 쓰면서 기록만 보낼 수 있다. 키(`LANGFUSE_*`)가 없으면 켜도 보내지 않고 이유를 알린다. 다음 change(호출 기록 자동 전송)도 이 설정을 쓴다.
8. **보내기 실패는 평가를 막지 않는다.** 평가는 저장·보고서까지 끝나고 "[Langfuse 실험] 보내지 못함: 이유". 화면 평가는 결과 상자에 같은 이유.
9. **화면 주소.** 프로젝트 id는 `GET /api/public/projects`(data[0].id), 데이터셋 id는 데이터셋 조회·만들기 응답 `id`에서 얻어 `<호스트>/project/<프로젝트>/datasets/<데이터셋>`. 얻지 못하면 주소만 비운다.

## 버린 대안

- `POST /api/public/dataset-run-items`(실행 이름으로 trace를 잇는 예전 방식): 문서가 더 쓰지 말라고 한다.
- Langfuse Python SDK의 실험 실행기: 우리 평가 루프(동시 묻기·반복·주입 짝·기준선)를 SDK 루프로 바꿔야 하고 의존성·백그라운드 스레드가 는다. 끝난 결과를 공개 API로 옮겨 적는 편이 작다.
- 평가마다 새 데이터셋: 판끼리 비교가 데이터셋을 넘나들어 Langfuse 비교 화면을 못 쓴다.

## 위험

- 실제 self-host Langfuse로 끝까지 돌려 보지 못했다(이 환경에서 Langfuse 스택을 띄우지 못함). 문서의 속성 이름·요청 모양을 흉내 낸 가짜 서버로 시험했다. 실험 속성을 지원하는 Langfuse 판, 화면 주소 모양 [확인 필요].
- 반복 3·78문항이면 trace 요청 3번(반복마다 한 번에), 점수 요청 3번(배열), 항목 78개 upsert. 로컬 Langfuse면 몇 초.
