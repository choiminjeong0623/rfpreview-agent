## ADDED Requirements

### Requirement: TBE 준수표
시스템은 실행의 현재 판정 중 준수·일탈 후보·질의 후보·확인 필요를 판정 순서(일탈 → 질의 → 확인 필요 → 준수)로 모아 줄마다 항목, 고객 요구값 원문, 준수 여부(Comply / Deviation / Clarification / To be confirmed), 우리 제품값과 제품 코드, 원문 위치, 확정 또는 후보 표시를 담은 TBE 준수표를 만들고 엑셀 파일로 내려받게 해야 한다(SHALL). 원문 위치가 없는 판정은 넣지 않고(MUST NOT) 뺀 수를 알린다. 반려한 판정과 보증값 작성 판정은 넣지 않는다. 팀 가정 값이 든 줄에는 "팀 가정"을 붙인다. 같은 판정이면 같은 파일 내용이어야 한다.

#### Scenario: 후보 포함
- **WHEN** 일탈 후보 1줄을 확정하고 나머지는 확정하지 않은 실행의 TBE 준수표를 후보 포함으로 만들면
- **THEN** 첫 줄은 Deviation이고 "확정"이며, 확정하지 않은 줄은 "후보"이고 보증값 작성 판정은 없다

#### Scenario: 확정한 줄만
- **WHEN** 같은 실행의 TBE 준수표를 확정한 줄만으로 만들면
- **THEN** 확정한 판정만 들어 있다

#### Scenario: 엑셀 파일
- **WHEN** TBE 준수표를 영문으로 내려받으면
- **THEN** 파일 이름은 "TBE_<검토 번호>_후보포함.xlsx"이고 첫 시트의 머리 줄은 No., Item, Requirement, Compliance, Offered, Source, Status이며 줄 수는 미리보기와 같다

#### Scenario: 항목 언어
- **WHEN** 국문으로 만들면
- **THEN** 항목은 표준 항목 한글 이름(없으면 원문 항목명)이고 준수 여부는 준수·일탈·질의·확인 필요이다
