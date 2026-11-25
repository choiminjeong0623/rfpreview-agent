# Design: update-judge-key-human

## 결정

- **D1 update-synthetic-key-human과 같은 방식.** 정답 칸(번호·text·expected·product_code·ambiguous·note)은 그대로 두고 확인 기록 칸(판정·변경여부·변경항목·검수근거·만든 이)을 뒤에 더한다. `load_judge_key`는 `DictReader`라 남는 칸을 읽지 않는다. 만든 이는 CSV가 아니라 `DEMO_KEYS`의 사람 확인 값(True)으로 정한다.
- **D2 검수근거는 사람이 쓴 메모 그대로 두고 덧붙임.** 부록 B 11줄(20~30번)의 메모 "부록 B의 GIS 적용은 초안 전제(원문 미확인)"는 지우지 않고, 뒤에 "→ 11-25 원문 확인: 부록 B 표 머리가 TS-170-GIS라 GIS에 적용"을 붙였다. 파일 28 docx에서 "Appendix B — Project-Specific Datasheet" 바로 뒤 표의 머리 칸이 TS-170-GIS다.
- **D3 확인표.** 사람이 본 확인표는 저장소에 올리지 않는다(프로젝트 공유 폴더 `eval/합성RFP28_판정정답지_확인표.xlsx`). 표의 제품표 값·계산은 코드가 `product_master.csv`에서 채웠고, 30줄 모두 초안 정답과 같았다.

## 위험

- 판정 정답지 30줄 가운데 19줄이 팀 가정 비교값(차단 시간·누설률·부분 방전·점검 주기·수명, 내전압·투입 전류)으로 정해진다. 사람 확인은 "제품표 값으로 판정하면 이 답"이라는 확인이지, 팀 가정 값 자체의 확인은 아니다(CR-06, 문서 05에 적음).
