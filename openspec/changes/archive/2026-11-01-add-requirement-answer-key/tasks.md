## 1. 문서

- [x] 1.1 명세서 정답지·채점 "요구사항 정답지 [제안 11-01, B1]", 기획서 8장 11-01 B1

## 2. 구현

- [x] 2.1 마이그레이션 0027 (key_kind REQ, made_by AUTO, doc_name, value_raw·unit_raw, eval_score.req_key_id)
- [x] 2.2 `evaluation.load_key(kind=REQ, doc)`, `make_supplier_key`, CLI `make-answer-key`, `load-answer-key --kind --doc`
- [x] 2.3 K1·K2·K3·K10 채점, 판정 없는 검토도 후보, API `req_key_id`, `npm run gen:api`
- [x] 2.4 합성 154 kV GIS 정답지 CSV `data/seed/answer_keys/`
- [x] 2.5 정답지·채점 화면: 요구사항 정답지 고르기, 코드 자동 표시

## 3. 테스트

- [x] 3.1 Scenario마다 테스트, 검사 통과
- [x] 3.2 "RFP18 Electric Distribution"로 로컬 측정(K1·K2), 개발 기록에 남김
