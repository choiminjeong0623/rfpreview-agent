## 1. 정답지

- [x] 1.1 `synthetic_rfp28_req.csv`·`synthetic_rfp28_type.csv`를 사람 확인본으로 (확인 기록 칸 포함)
- [x] 1.2 28번 줄 검수근거 "4.3 TS-24-CB 7" → "4.2 TS-170-GIS 7" (design D3)

## 2. 코드

- [x] 2.1 `db/cli.py` `DEMO_KEYS`에 정답지마다 사람 확인 여부(요구사항·유형 True, 판정 False)

## 3. 시험과 문서

- [x] 3.1 `test_synthetic_answer_key.py` "합성 RFP 정답지 넣기": 만든 이 사람, 유형 사람 확인 65·애매함 19
- [x] 3.2 `test_synthetic_rfps.py`·`test_eval_demo.py` "합성 RFP 정답지 채점"·"재현 채점": K13 38/38, 만든 이
- [x] 3.3 `test_demo_setup.py` "빈 DB에 시연 준비": 만든 이
- [x] 3.4 `docs/05-evaluation.md` 0장 표와 정답지 설명
