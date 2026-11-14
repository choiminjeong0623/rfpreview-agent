# Design

## 결정

- **표** `doc_kind_rule(doc_kind_rule_id, priority UNIQUE, doc_kind, name_pattern, page_pattern NULL, note)`. 마이그레이션 0012.
  문서 종류는 `document.doc_kind`와 같은 6종 CHECK(UNKNOWN 빼고 5종만 규칙이 될 수 있다).
- **CSV** `data/seed/doc_kind_rules.csv`: `priority,doc_kind,name_pattern,page_pattern,note`. 지금 `KIND_RULES` 5줄을 순서 그대로 옮긴다.
  표현은 파이썬 정규식이다. 파일 이름 표현은 소문자 파일 이름에, 첫 장 표현은 대소문자 무시로 찾는다(지금과 같음).
- **적재** `seed_doc_kind_rules`: 줄마다 `re.compile`과 종류 코드를 확인하고, 틀리면 `SeedError`(줄 위치). 다른 사전처럼 지운 뒤 다시 넣는다.
- **분류** `classify(file_name, blocks, catalog, kind_rules)`. `kind_rules`는 `dictionaries.load`와 `preview`가 DB에서 읽는다. 코드 안 목록은 지운다(한 곳에서만 관리).
  규칙 id(`K-NAME-<종류>`, `K-PAGE-<종류>`)는 그대로라 이전 결과와 같은 이름이다.
- **사전 판**: `dict_version`이 `data/seed`의 모든 CSV를 해시하므로 새 파일이 생기면 판이 바뀐다. 다음 실행에서 문서를 다시 처리한다(한 번).
- **조회** `GET /api/rules/doc-kinds` → `DocKindRule`(priority, doc_kind, name_pattern, page_pattern, note, used).
  `used`는 그 종류로 `classify_by = 'RULE'`인 문서 수(문서마다 어느 줄이 맞았는지는 저장하지 않는다. 같은 종류는 한 줄뿐이라 같은 뜻).
- **화면** 판정 규칙(SCR-17)에 "문서 종류" 탭. 칸: 문서 종류, 파일 이름에서 찾는 표현, 첫 장에서 찾는 표현, 순서, 분류한 문서. 펼치면 메모와 "파일 이름 먼저, 그다음 첫 장" 설명.

## 대안

- 표현을 정규식 대신 단어 목록으로 → 지금 규칙("spec\\." 같은)을 그대로 옮길 수 없다.

## 위험

- 사전을 잘못 고치면 모든 문서 종류가 바뀐다 → 적재 때 정규식 검사, 결과는 문서 표에서 "분류 방법"과 함께 보인다.
