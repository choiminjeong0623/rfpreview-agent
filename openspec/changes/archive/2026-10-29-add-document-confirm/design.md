# Design

## 결정

- **추천 API**: `POST /api/runs/preview`(multipart `files`)와 `POST /api/runs/library/preview`(`{"files": [...]}`). docx를 읽어 `classify.classify`만 돌린다.
  DB에는 아무것도 쓰지 않는다(파일은 시작 때와 같은 해시 폴더에 둔다. 같은 파일을 다시 올려도 한 번만 저장). 언어 모델은 부르지 않는다.
  분석 중 AI 종류 보조(`apply_ai_kind`)는 그대로라 추천 화면과 결과의 문서 종류가 다를 수 있다. 그때는 지금처럼 "확인 필요".
- **목록 밖 문서의 묶음 추천** (`classify.suggest_bundle`): 읽을 수 있고 `standard_system == "IEC"`면 B, 그 밖 C. [제안]
  이유: 제품표(product_master)가 IEC 정격 제품이다. 묶음 A는 사업 데이터시트(입찰 서식) 묶음이라 목록으로만 정하고, D는 한국 사업 묶음이라 자동으로 고르지 않는다.
  이 추천은 등록 화면에만 쓴다. 등록 화면 없이 API로 시작하면(`choices` 없음) 지금처럼 목록 밖 문서는 C다 — 사람이 보지 않은 문서를 판정하지 않기 위해(CR-08).
- **사람 값 저장** (`classify.apply_choice`): `choices`는 파일 이름 → `{bundle, doc_kind}`. 규칙 결과와 다르면 `classify_by = 'HUMAN'`, `needs_review = false`,
  `judge_target = bundle in (A,B) and readable`. 같으면 규칙 결과 그대로(재사용 유지).
- **재사용과 처리 판**: 문서 행은 (파일 경로, 처리 판 `processing_key`)로 재사용한다. 사람 값이 규칙과 다르면 처리 판 뒤에 `|H:<묶음>:<종류>`를 붙여
  다른 문서 행으로 처리한다. 같은 파일을 다른 묶음으로 시작해도 이전 검토의 문서를 바꾸지 않는다(CR-11). 대신 그 문서는 다시 처리한다(AI 비용).
  새 마이그레이션은 필요 없다(`classify_by`에 이미 HUMAN이 있다).
- **사람이 문서 종류를 정하면** AI 종류 보조를 건너뛴다.
- **화면**: 등록 표의 "분석하면서 정합니다" 칸을 문서 종류 고르기 · 묶음 고르기 · 언어로 바꾼다. 판정 칸에 "판정 대상"/"판정 안 함"과 이유, 바꾼 줄은 "사람이 바꿈".
  파일을 더하거나 뺄 때마다 아직 추천이 없는 파일만 불러온다. 시작할 때 모든 줄의 값을 `choices`로 보낸다(서버가 규칙과 같은 값은 무시).
  multipart에는 `choices`를 JSON 글자 칸으로 보낸다.

## 대안

- `document_catalog`에 줄을 더하기 → 팀 정답 명단을 검토마다 고치게 되어 버림.
- `run_document`에 검토별 묶음 칸 → 판정·출력 질의 여러 곳이 `document.judge_target`을 보므로 바꿀 곳이 많다.

## 위험

- 수백 쪽 docx는 읽기에 몇 초 걸린다. 파일마다 따로 부르지 않고 한 번에 보낸다.
- 추천(규칙)과 분석 중 AI 보조 결과가 다르면 문서 종류가 바뀔 수 있다 → 문서 표에 "확인 필요".
