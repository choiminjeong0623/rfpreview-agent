# Proposal

## Why

목업 v4.96(v4.93부터)은 판정 줄을 누르면 뜨던 판정 창을 **판정 상세 전용 화면**(`#/reviews/:id/judgments/:jid`)으로 바꿨다. 화면 하나를 통째로 써서 원문을 앞뒤 줄과 함께 읽고, 비교 근거·판정 출처·신뢰도를 처음부터 보이며, 주소로 다른 사람에게 그 판정을 가리킬 수 있다.
지금 판정 창은 그 요구 문장 한 줄만 보여 "이 문장이 어느 문맥에 있는지"를 보려면 원문 파일을 따로 열어야 한다. 서버에는 앞뒤 줄을 돌려주는 API가 없다.
프런트 4단계 3번(`docs/screens/_v4.96_결정.md` 1장 Q2, 3장 원문 줄 범위 API, 4장 3번). 화면 명세 `docs/screens/SCR-08-12-판정상세.md`.

## What Changes

- 새 API `GET /runs/{id}/documents/{file_no}/lines?from=&to=`: 그 검토 문서의 원문 줄(최대 40줄)을 분석 때와 같은 줄 번호로 돌려준다. 올린 파일이 없으면 DB에 남은 줄(절 제목·요구 문장·표 행)만 돌려주고 `partial: true`.
- 새 화면 판정 상세 `#/reviews/:id/judgments/:jid?f=&unc=&q=&type=&past=&page=&size=`: 판정 목록의 거르기를 주소로 받아 이전·다음 판정(↑↓)과 "판정 n / 전체"를 정한다. 판정 목록으로(Esc) 가면 같은 거르기·같은 쪽, 보던 줄을 오른쪽 패널에 연다.
- 원문: 파일 이름·언어, 위치 탭(위치가 둘 이상일 때), 절 번호·제목, 그 줄 앞뒤 2줄(그 줄 강조·요구값 표시), 표 위치는 표 한 줄(No.·Description·Unit·Employer's Req.·Warranted).
- 비교·판정 근거: 요구값·부등호·제품값, 비교 방향 + 판정 규칙 보기, 적용 규칙, 같은 요구 위치 수, 제품값 출처(제품표 출처 문서)와 "팀 가정", 유형, 공학 검산.
- 판정 출처: 시스템 제안, 찾은 방법(코드 규칙·AI)과 신뢰도, 담당자 확정, 지난 확정.
- 질의 후보는 "질의 초안" 꼬리표, 목록 문장(SCR-08-11 문장 고치기 그대로), 보증값 작성은 후보 값과 [데이터시트에서 쓰기].
- 아래 줄: 판정 바꾸기(창: 새 판정·사유 필수)·제안대로 확정(확정 뒤 다음 확정 안 한 판정으로). 담당자 확인 단계의 엔지니어가 아니면 잠그고 이유를 보인다.
- 판정 탭에서 줄을 누르면 이 화면으로 간다. 판정 창(`JudgmentDialog`)을 없앤다. 판정 규칙 화면은 `#/rules?q=`로 검색어를 받는다.

## Non-Goals

- 질의 보냄 표시·되돌리기(`add-query-sent`, 4장 8번). 이번에는 "질의 초안" 꼬리표만.
- 번역(갭 목록 G7), 비슷한 요구의 과거 입찰 결과(Q6 범위 밖).
- 이 화면에서 보증값 쓰기(데이터시트 화면에서만).
- 판정 탭 칩·표 모양의 v4.96 정리(꼭 볼 것 칩 등): 개정 안내 띠(`add-revision-notice`)와 함께.

## Impact

- 백엔드: `pipeline/source_lines.py`(새), `api/runs.py` 한 경로, `api/schemas.py` `DocumentLines`. 마이그레이션 없음.
- 프런트: `views/JudgeView.tsx`(새), `mockup/JudgeView.css`(v4.96 JudgeView 규칙만), `App.tsx` 경로, `detail/JudgeTab.tsx`, `views/Rules.tsx` 검색어, `api.ts`·`openapi.json`·`api.gen.ts`.
- 명세: `review-workspace`(ADDED 3, MODIFIED 1), `evidence-integrity`(ADDED 1).
