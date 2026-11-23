# Design: add-eval-demo

## Context

- 정답지는 `answer_key`(종류 TYPE·REQ)와 `answer_key_row`(text_raw, expected, ambiguous, value_raw, unit_raw)에 있다(0022·0027). 채점은 `evaluation.metrics`가 지표 dict 목록을 만들고 `eval_score.metrics`에 JSON으로 저장한다.
- 요구사항 정답지 채점(`req_eval`)은 정답 줄과 시스템 요구사항을 `same_line`(공백·대소문자 무시, 품기 30자, 표 칸 하나)으로 맞추고, 대상 문서는 `doc_name`이 파일 이름에 든 문서로 좁힌다.
- 파일 28은 파일 24 → 25 → 26 → 27 → 28로 만든다. 파일 25 스크립트가 공개본에 없다.

## Goals / Non-Goals

목표: 남이 저장소만 받아 한 명령으로 같은 숫자를 다시 내게 하고, 판정 정확도를 사람 확정 없이도 잴 수 있게 하고, 표본 크기를 숫자 옆에 보인다.
아닌 것: 정답지의 사람 확인, AI 켠 측정, 실제 RFP 측정.

## Decisions

### D1. 판정 정답지는 기존 표에 종류를 더한다

`answer_key.key_kind`에 `JUDGE`, `answer_key_row.product_code`(VARCHAR(40), 비어도 됨), `eval_score.judge_key_id`를 더한다(0048). `expected`는 VARCHAR(20)이라 `DEVIATION_CANDIDATE`(19자)가 들어간다.
- 버린 대안: 판정 정답지 표를 따로 만들기. 정답지 목록·채점 기록·화면이 이미 `answer_key` 하나를 보므로 따로 두면 세 곳을 모두 고쳐야 한다.

### D2. 줄 맞추기는 요구사항 정답지와 같은 규칙

판정 줄의 요구사항 원문(`requirement.text_raw`)을 정답 줄과 `req_eval.same_line`으로 맞춘다. 정답 줄을 번호 순서로 보며 각 줄은 아직 쓰지 않은 지금 판정 중 요구사항 번호가 가장 작은 것 하나를 가져간다(한 판정은 한 정답 줄에만, CR-11). 대상 문서는 `scope_documents`로 좁힌다.
- 4.2 표 7번 줄과 4.3 표 7번 줄은 글자가 같다("7 / Total Breaking Time / ms / ≤60 ms"). 정답 줄을 문서 순서로 적어 두면 위 규칙으로 4.2 줄은 4.2 판정, 4.3 줄은 4.3 판정과 맞는다. 정답지 줄 순서가 문서 순서라는 것을 정답지 규칙으로 적는다.
- 부록 B 표 줄은 번호가 `D-01`처럼 달라 4.2 줄과 겹치지 않는다.

### D3. 정답이 맞았다는 기준

- 판정 값이 같아야 하고, 정답 줄에 `product_code`가 있으면 시스템 판정의 비교 제품도 같아야 한다. 확인 필요(비교 제품 없음)가 정답인 줄은 제품을 보지 않는다.
- 애매한 줄(`ambiguous`)은 K5-정답지 분모에서 빼고 따로 센다(유형 정답지와 같다).
- K6-정답지: 정답이 `DEVIATION_CANDIDATE`인 애매하지 않은 줄 중 시스템도 `DEVIATION_CANDIDATE`인 비율(제품 무관).
- 못 찾은 줄(맞는 판정 없음)은 시스템이 판정을 내지 않은 것이므로 K5-정답지 분모에 넣고 틀린 것으로 센다. 판정을 내지 않은 것도 놓친 것이기 때문이다. 표에는 시스템 칸 "없음"으로 보인다.

### D4. 판정 정답지 초안 만드는 법 (합성 RFP 28, 30줄)

시스템 결과를 보지 않고, 문서의 요구값과 `data/seed/products/product_master.csv`를 손으로 비교했다.
- 4.2 TS-170-GIS 1~11: 제품표에 170 kV GIS는 GIS-170-50 하나. 요구값이 모두 제품값과 같거나 느슨해 11줄 준수.
- 4.3 TS-24-CB 1~7: 24 kV·40 kA 진공차단기가 정격 전류만 다른 5개라 사람이 고르기 전에는 비교 제품을 정할 수 없다 → 확인 필요(제품 없음). 이 결정은 메모에 적는다.
- 부록 B D-01~D-11: GIS-170-50과 비교해 D-02(≥4000 A, 제품 4000 A)만 준수, 나머지 10줄 일탈 후보.
- 9.3 문장 "annual gas leakage rate … shall not exceed 0.5 %": GIS 문장이고 GIS-170-50 값이 0.5 %라 준수. 시스템이 표 밖 문장의 비교 제품을 잇지 못하면 틀린 것으로 잡힌다(알고 있는 빈틈을 정답지가 드러냄).

### D5. 윌슨 95 % 구간

`z = 1.96`, `center = (p + z²/2n) / (1 + z²/n)`, `half = z·sqrt(p(1−p)/n + z²/4n²) / (1 + z²/n)`. 백분율 소수 첫째 자리로 반올림. 분자·분모가 있는 `%` 지표에만 붙인다(K11·K12·처리 시간 제외). `_metric`이 계산하므로 모든 지표가 같은 규칙.
- 버린 대안: 정규 근사(Wald). 100 %·작은 n에서 구간 폭이 0이 되어 이 문제를 못 보인다.

### D6. 재현 채점 명령

`rfp-db eval-demo [--create] [--report 파일]`은 `RFP_AI_MODE=off`로 바꾼 뒤 `demo_setup`(검토가 있는 DB 거절은 그대로)을 부르고, 판정 정답지를 넣고, `evaluation.metrics`로 세 정답지 채점(채점 기록에도 저장, 메모 "eval-demo")을 한다. 출력 표는 처리 시간을 넣지 않는다(기계마다 다름). 맨 위에 코드 판(`code_version`)과 정답지 만든 이를 적는다.
- 같은 결과 보장: AI 끔, 같은 파일, 같은 규칙 사전·제품표(저장소), 채점은 코드만.

### D7. CI에서 합성 문서 만들기

backend 작업 pytest 앞에 `uv run python ../generate_{evaluative,deviation,collaboration,risk,switch}_rfp.py`를 돌린다. 생성 파일은 `data/private/rfp_docx/`에 생기고 커밋되지 않는다(.gitignore). 이로써 `test_synthetic_rfps.py`·`test_synthetic_answer_key.py`와 새 재현 테스트가 CI에서 돈다.

### D8. 다시 만든 파일 28의 K2

공개본 스크립트로 만든 파일 28은 원래 파일과 표 줄·문장이 같지만 원래 부록 B 앞 설명 문단이 없어, 시스템이 뽑은 요구사항이 67줄이 아니라 66줄이다(정답지에 없는 줄: 5장 "Evaluation Committee shall score …" 1줄). K2를 65/67 → 65/66으로 시나리오·테스트·문서에서 바꾼다. 원래 문단 글은 남아 있지 않아 지어내지 않는다.

## Risks / Trade-offs

- 판정 정답지도 Claude 초안이다. 정답 근거가 단순 비교라 틀릴 여지는 작지만, 사람 확인 전까지 K5-정답지는 "Claude 초안 기준"으로 적는다. 사용자가 확인할 시트를 따로 만든다.
- 합성 문서는 시스템을 만든 사람이 만든 문서라 실제 문서보다 쉽다. docs/05에 그대로 적는다.
