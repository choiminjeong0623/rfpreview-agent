## 1. 추출 규칙 (BE 나송주)
- [x] 1.1 `extract.py` MARK_TABLE_ROWS(문서에 표시가 있으면 표 조항 줄을 공급사 답안 후보), FORM_NOTES(입찰 서식 작성 안내 → 작성 규칙, 위험 표현 문장 제외)
- [x] 1.2 `processors.py` 처리기마다 `rules`, `_prepare`가 규칙과 위험 표현을 넘김

## 2. 시험과 측정 (BE 나송주)
- [x] 2.1 Scenario마다 테스트(`tests/test_kind_extract_rules.py`), 기존 추출·정답지 테스트 통과
- [x] 2.2 로컬 K1·K2 전후 측정을 design·PR에 기록

## 3. 마무리 (나송주)
- [x] 3.1 AGENTS.md 표, 추적표, archive
