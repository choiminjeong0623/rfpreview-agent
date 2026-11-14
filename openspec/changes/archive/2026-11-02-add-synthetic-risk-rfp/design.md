# 설계: add-synthetic-risk-rfp

## 결정

### 1. 파일 27 만들기 (`generate_risk_rfp.py`, 저장소 루트)
- `generate_collaboration_rfp.py`와 같은 방식: 파일 26을 열어 "Appendix A" 앞에 9장을 넣고 `RFP_Product_Master_Evaluative_EN_With_Risk_Clauses.docx`로 저장(data/private/rfp_docx, 커밋 안 함).
- 위험 조건이 후보가 되려면 표현이 맞는 절 제목 안에 있어야 한다(`risk.CONTEXT_WORDS`). 9장 제목에 contract·deviation·scope·supply를 모두 넣고, 절마다 한 종류씩:
  - 9.1 Deviations and Clarifications (BLANKET): "… shall be deemed to be accepted …", "No deviations … will be accepted after contract award."
  - 9.2 Scope of Supply (OPEN_SCOPE, COST_SHIFT): "… including but not limited to …", "… at no extra cost to the Procuring Entity."
  - 9.3 Technical Clarifications (VALUE_MISMATCH): "The annual gas leakage rate of each gas compartment of the GIS shall not exceed 0.5 %." — 파일 25의 부록 B 데이터시트는 0.4 %. 같은 문서의 문장 값과 표 값이라 값 불일치 조건(같은 항목·단위·적용 대상, 한쪽은 표가 아님)에 맞는다.
- 표지 표의 "Document purpose"에 위험 조항 검토 항목을 더한다.

### 2. 문서 목록·문서 종류 규칙
- `data/seed/document_catalog.csv` 27번 줄: `RFP_Product_Master_Evaluative_EN_With_Risk`, B, en. 목록 찾기는 가장 긴 표현이 이기므로 파일 24·25·26 줄과 섞이지 않는다.
- `data/seed/doc_kind_rules.csv` 7번 줄: `REQUIREMENT_SPEC`, 파일 이름 `rfp_product_master`. 앞 줄(입찰 서식·공급사·시험·구매·요구 사양서·물량표)에 걸리지 않는 합성 RFP 23~27만 걸린다. 순서는 맨 뒤(사람 고침 이력과 어긋나지 않게).
- 문서 종류가 바뀌어 처리기(요구 사양서: 설명·"요구사항 0줄" 점검)가 바뀐다. 처리 판은 사전 판이 바뀌어 저절로 새로 분석된다.

### 3. 시험
- 문서 종류 규칙 줄 수 6 → 7(`test_doc_kind_rules`).
- `tests/test_synthetic_rfps.py`: 합성 RFP 원문(data/private)이 있을 때만 돈다(`test_corpus`와 같음). 분류와 파일 27 결과(위험 3종·일탈 10·협조 요청).
- 문서 목록 줄 수를 세는 테스트가 있으면 26 → 27.

## 위험
- CI에는 합성 RFP 원문이 없어 시나리오 테스트가 건너뛴다. 로컬(원문 있음)에서 확인하고 PR에 결과를 적는다.
