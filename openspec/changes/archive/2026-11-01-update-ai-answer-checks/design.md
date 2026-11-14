# 설계

## 번호 붙인 답

- 스키마: `labels`·`types`는 `[{n: 정수, v: 보기}]`, `texts`는 `[{n: 정수, text: 문장}]`. n은 묻는 글의 줄 번호(0부터)와 같다.
- 검사(`check`)는 n을 모아 정렬한 것이 `0..len-1`과 같아야 통과. 통과하면 n 순서로 다시 줄 세운다. 그래서 모델이 순서를 섞어 내도 같은 결과(CR-11).
- 대안: 줄 원문 앞 몇 글자를 같이 받기 — 토큰이 늘고 긴 줄에서 비교가 흔들려 뺐다.
- 묻는 글의 번호 매김과 PROMPT_VERSION은 그대로 둔다. 같은 문서 재사용 키(처리 키)에 PROMPT_VERSION이 들어가므로, 답 형식만 바꾼 이번에는 판을 올리지 않는다. 기존 처리 결과는 줄마다 이미 맞춰 저장된 값이라 그대로 쓸 수 있다.

## 필수 자리표시자

- `draft_sentences`는 줄마다 `str | None`을 돌려준다. None은 "이 줄은 AI 문장을 쓰지 않음".
- 줄 검사: 비지 않음, 경쟁 비교 없음, `set(자리표시자) == set(marks)`.
- 형식 오류(번호·개수)는 여전히 다시 묻는다. 줄 내용 오류는 다시 묻지 않고 그 줄만 기본 문장으로: temperature 0이라 같은 질문에는 같은 답이 나오기 쉽고, 한 줄 때문에 검토 전체가 멈추던 문제를 없앤다.
- 호출하는 곳(outputs `_texts`, proposals `build_proposals`)은 None이면 `(template, "CODE")`.

## 숫자 허용 좁히기

- 문장(claim)마다 `allowed = 숫자(facts + 그 문장이 댄 근거 조각들)`.
- 배수 말: 정규식 `(두|세|네|다섯|열)\s?배|절반|twice|double|triple|half`(대소문자 무시). 문장에 있는데 facts와 그 문장의 근거 조각에 같은 말이 없으면 버린다.
- 위험: 근거가 영어이고 설명이 한국어라 "절반"은 근거의 "half"와 짝이 안 맞아 버려질 수 있다. 안전한 쪽(버림)으로 둔다.

## 버린 이유

- `explain_risk`는 `RiskExplanation | DroppedExplanation(reason)`을 돌려준다. 이유는 처음 걸린 것 하나.
- `risk_flag.explanation_drop_reason VARCHAR(30)` (0024). 다시 쓴 설명(이어받기)은 이유를 비운다. 언어 모델 없이 돈 실행도 비운다.
- 실행 기록: `run_log`에서 `count(*) FILTER (WHERE explanation_drop_reason IS NOT NULL)`을 `explanations_dropped`로 준다(저장 칸 따로 두지 않음).
- 위험 조건 API 응답에 `explanation_drop_reason`을 더한다. 화면은 설명 대신 "AI 설명을 버림 — 근거에 없는 숫자"처럼 보인다.
