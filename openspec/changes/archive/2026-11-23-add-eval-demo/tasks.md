## 1. 합성 RFP 다시 만들기

- [x] 1.1 `generate_deviation_rfp.py`(파일 24 → 25, 부록 B TS-170-GIS D-01~D-11)
- [x] 1.2 테스트: 스크립트로 만든 파일 25에 부록 B 표 11줄 (Scenario: 스크립트로 합성 RFP 만들기)
- [x] 1.3 K2 65/67 → 65/66: `test_synthetic_rfps.py`, 문서

## 2. 판정 정답지 (0048)

- [x] 2.1 마이그레이션 0048: 종류 JUDGE, `answer_key_row.product_code`, `eval_score.judge_key_id`
- [x] 2.2 `judge_eval.load_judge_key`·`rfp-db load-answer-key --kind JUDGE --doc` (Scenario: 판정 정답지 넣기, 잘못된 판정 값)
- [x] 2.3 `data/seed/answer_keys/synthetic_rfp28_judge.csv` 30줄 (design D4)
- [x] 2.4 `judge_eval.scores`: K5-정답지·K6-정답지·혼동표 (Scenario: 판정 정답지 채점, 다른 비교 제품)
- [x] 2.5 `evaluation.score`·API `judge_key_id`, 응답 `judgments`, 정답지 목록 JUDGE

## 3. 신뢰 구간

- [x] 3.1 `evaluation.wilson`, `_metric`이 `ci_low`·`ci_high` (Scenario: 작은 표본의 구간)
- [x] 3.2 스키마 `EvalMetric`·`EvalMetrics`, `npm run gen:api`

## 4. 재현 채점 명령

- [x] 4.1 `rfp-db eval-demo [--create] [--report]` (design D6)
- [x] 4.2 테스트: 새 DB 두 곳에서 같은 표 (Scenario: 재현 채점), 합성 정답지 채점 (Scenario: 합성 RFP 정답지 넣기·채점)
- [x] 4.3 `demo-setup`이 판정 정답지도 넣음

## 5. 화면

- [x] 5.1 `Eval.tsx` 판정 정답지 고르기, 구간 표시 (Scenario: 판정 정답지로 채점)
- [x] 5.2 e2e `evaluation.spec.ts` "판정 정답지로 채점"(응답은 page.route), 기존 "지금 채점하기" 라디오 찾기 고침

## 6. CI·문서

- [x] 6.1 CI backend: pytest 전에 합성 RFP 24~28 만들기
- [x] 6.2 `docs/05-evaluation.md` 재현 방법·표, README·setup 명령
- [x] 6.3 사람이 확인할 정답지 확인 시트(요구사항·유형·판정 세 장, 저장소 밖 프로젝트 파일로 전달)
