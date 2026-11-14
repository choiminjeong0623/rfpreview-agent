## MODIFIED Requirements

### Requirement: 쪽 넘김 표 잇기
시스템은 머리글 줄과 표 이름이 같고 항목 번호가 이어지는 Word 표들을 한 표로 이어야 한다(SHALL). 쪽마다 반복되는 머리글 줄은 행으로 저장하지 않아야 한다(SHALL). 표 안에 표 이름이 없으면 표 바로 앞 단락이 150자 이하이고 표 이름으로 시작할 때 그 이름을 표 이름으로 써야 하며, 본문 속 표 이름 언급은 쓰지 않아야 한다(SHALL).

#### Scenario: 4개로 나뉜 115 kV GIS 표
- **WHEN** 쪽 넘김으로 여러 Word 표에 나뉜 파일 1의 115 kV GIS 표를 나누면
- **THEN** 표 TS-115-GIS 하나에 첫 구분(I)의 항목 1~27이 이어지고 반복 머리글 줄은 행으로 나오지 않는다

#### Scenario: 표 바로 앞 단락의 표 이름
- **WHEN** 제목 줄 없는 표 앞에 "TS-170-GIS — Added deviation-candidate requirements" 단락이 있고, 다른 표 앞에는 "Refer to TS-245-GIS for the other bay." 단락이 있으면
- **THEN** 첫 표의 이름은 TS-170-GIS이고 둘째 표는 이름이 없다
