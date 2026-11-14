## 1. 문서 재사용 조건

- [x] 1.1 `0015_document_content_hash.sql`: document.content_hash, 고유 색인 바꾸기
- [x] 1.2 document.py: 내용 지문을 저장하고 재사용 조회에 넣기
- [x] 1.3 테스트: 같은 이름·다른 내용이면 새로 처리, 같은 내용이면 재사용

## 2. 표 이름 단락

- [x] 2.1 structure.py: 표 바로 앞 단락을 표 이름으로 쓰기(150자 이하, 표 이름으로 시작)
- [x] 2.2 테스트: 앞 단락 "TS-170-GIS — …"는 이름, "Refer to TS-…"는 이름 아님

## 3. 빈 목록 초안 거절

- [x] 3.1 runs.py: 목록 항목(뺀 항목 제외)이 없으면 409
- [x] 3.2 테스트: 항목을 모두 빼면 409와 "후보가 없습니다"
- [x] 3.3 `npm run gen:api`

## 4. 시험 자료·개발 환경

- [x] 4.1 document_catalog.csv 25·26번, generate_collaboration_rfp.py
- [x] 4.2 docker-compose VITE_USE_POLLING, vite.config.ts 폴링
