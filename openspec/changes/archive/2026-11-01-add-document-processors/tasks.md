## 1. 처리기 표와 AI 질문
- [x] 1.1 `pipeline/processors.py` 처리기 표(종류·이름·설명·점검)
- [x] 1.2 `label_sections`·`type_unclassified`에 문서 종류 설명, `PROMPT_VERSION` p5
- [x] 1.3 마이그레이션 0030: `document.processor`·`process_check`·`reprocessed`

## 2. 점검 뒤 한 번 다시 처리
- [x] 2.1 `_prepare` 뒤 점검(메모리 줄 수), 걸리면 일반 처리기로 한 번 더 준비 [구현 때 바뀜: design 3장]
- [x] 2.2 문서 행 기록·`needs_review`, 문서 표 응답 칸, 실행 기록 `documents_reprocessed`, `npm run gen:api`

## 3. 문서 병렬 처리
- [x] 3.1 설정 `RFP_DOC_WORKERS`(기본 2), `documents` 노드 스레드 처리(스레드마다 연결)
- [x] 3.2 저장은 차례표로 올린 순서대로(같은 요구 묶기·번호가 차례 처리와 같음) [구현 때 바뀜: design 4장]
- [x] 3.3 실패·취소: 나머지 문서 저장 뒤 첫 오류

## 4. 시험과 마무리
- [x] 4.1 Scenario마다 테스트(`tests/test_document_processors.py`)
- [x] 4.2 AGENTS.md 표, 개발 기록, archive
