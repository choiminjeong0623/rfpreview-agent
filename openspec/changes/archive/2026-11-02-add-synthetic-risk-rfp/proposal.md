# 시연용 합성 RFP에 위험 조항 넣기

## 왜

- 팀은 실제 RFP 22개 대신 팀이 만든 합성 RFP(파일 23~26, 제품표 기반 docx)로 시연·평가한다(2026-11-02).
- 합성 RFP 4개를 지금 main으로 돌려 보니(AI 끔) 일탈 후보(파일 25: 10건)·협조 요청(파일 26: 견적·품질·영업 3건씩)은 의도대로 나오지만, **위험 조건은 4개 모두 0건**이다. 합성 문서에 위험 표현(deemed, at no extra cost, including but not limited to …)이 하나도 없고 값 불일치도 없다. 시연에서 FR-06(위험 조건 찾기)·AI 설명 검증·사전 추가 제안이 보이지 않는다.
- 또 합성 RFP 4개는 파일 이름이 문서 종류 규칙에 걸리지 않아 모두 "종류 모름"(일반 처리기)이다.

## 무엇

- **파일 27(위험 조항 변형)**: 파일 26에 "9. Contract Conditions, Deviations and Scope of Supply"를 더한 합성 RFP. 계약·일탈 조항에 포괄 조항(deemed, no deviations), 공급 범위 조항에 범위 모호(including but not limited to)와 비용 전가(at no extra cost), 기술 확인 조항에 가스 누설률 0.5 %(데이터시트는 0.4 %) 값 불일치. 만드는 스크립트 `generate_risk_rfp.py`(파일 26 → 27, 결과는 data/private).
- **문서 목록**에 파일 27(묶음 B) 한 줄.
- **문서 종류 규칙** 7번 줄: 파일 이름 `rfp_product_master` → 요구 사양서(합성 RFP 23~27).

## 하지 않음

- 시스템 동작 변경(위험 조건 규칙·사전은 그대로). 합성 데이터와 사전 줄만 더한다.
- 파일 24~26 고치기(팀원 자료). 새 파일 27만 만든다.

관련: 명세서 8장 시연용 합성 RFP, FR-06, 이전 데이터 `generate_evaluative_rfp.py`·`generate_collaboration_rfp.py`.
