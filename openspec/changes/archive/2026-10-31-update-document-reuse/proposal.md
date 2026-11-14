## Why

박경빈 브랜치(KB/RFP/retouch)에서 찾은 문제 세 가지를 지금 main 위에 옮긴다.

- 같은 파일 번호(파일 목록에서 이름으로 찾음)와 같은 처리 판이면 저장된 결과를 다시 썼다. 그래서 이름만 같고 내용을 고친 RFP(예: 일탈 후보를 더한 판)를 올려도 예전 분석 결과가 나왔다.
- 표 제목 줄이 표 안이 아니라 바로 앞 단락("TS-170-GIS — …")에 있으면 표 이름을 못 찾아, 쪽 넘김 표 잇기와 원문 위치 표시가 약했다.
- 일탈·질의 후보가 하나도 없는데 초안 Word 파일을 요청하면 빈 파일이 만들어졌다. 화면 버튼은 이미 잠기지만(PR #36) API도 막아야 한다.

관련: NFR-05, FR-02, SCR-08-11, CR-02.

## What Changes

- 저장된 처리 결과는 처리 판과 **파일 내용(SHA-256)**이 모두 같을 때만 다시 쓴다. 문서 행에 내용 지문을 저장한다(마이그레이션 0015).
- 표 안에 표 이름이 없고 바로 앞 단락(150자 이하)이 표 이름으로 시작하면 그 단락을 표 이름으로 쓴다. 본문 속 언급("Refer to TS-…")은 쓰지 않는다.
- 목록에 올릴 항목(뺀 항목 제외)이 없으면 초안 Word 파일 요청을 409로 거절한다.
- 파일 목록에 시험용 합성 RFP 25·26번을 더하고, 26번을 만드는 스크립트(`generate_collaboration_rfp.py`)를 둔다. 합성 docx는 `data/private/rfp_docx/`에 두고 커밋하지 않는다.
- Docker 개발 서버가 윈도우·맥에서 파일 바뀜을 알아채도록 폴링을 켠다(동작 변화 없음).

## Impact

- 스펙: review-run, document-intake, bid-outputs
- 코드: pipeline/document.py, pipeline/structure.py, api/runs.py, data/seed/document_catalog.csv, docker-compose.yml, frontend/vite.config.ts
- DB: db/migrations/0015_document_content_hash.sql. 받은 뒤 `rfp-db setup`. 예전 문서 행은 지문이 비어 있어 다음 실행 때 한 번 새로 처리한다.
