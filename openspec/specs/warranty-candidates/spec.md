# warranty-candidates Specification

## Purpose
데이터시트 요구값 칸의 약 39 %가 빈칸이다. 이 칸에 근거 있는 우리 값만 후보로 채워 엔지니어의 반복 입력을 줄인다 (FR-08).

## Requirements

### Requirement: 연결표에 있는 항목만 후보
시스템은 판정이 "보증값 작성"인 행에 대해 항목 → product_master 연결표에 있는 항목만 product_master 값이나 회사 고정값으로 후보를 내고 출처를 남겨야 한다(SHALL). 값이 없으면 비워 두고 "확인 필요"로 표시해야 한다(SHALL). "comply" 같은 말은 후보로 쓰지 않는다(MUST NOT).

#### Scenario: 회사 고정값
- **WHEN** TS-115-GIS 1번 "Manufacturer's name"이 빈칸이면
- **THEN** 후보 "LS ELECTRIC", 출처 = 회사 고정값이다

#### Scenario: 제품표에 없는 값
- **WHEN** 20번 "외함 온도 상승"이 빈칸이고 product_master에 값이 없으면
- **THEN** 후보는 비어 있고 상태는 확인 필요이다 (K11 = 0)

#### Scenario: 제품표 값
- **WHEN** 파일 1 TS-SG "Weight of complete 3-phase breaker"가 빈칸이고 비교 제품이 VCB-SUSOL-24-40-3150이면
- **THEN** 후보 318 kg, 출처 = product_master weight_kg이다

### Requirement: 제품 행이 여럿일 때
시스템은 같은 항목에 맞는 제품 행이 여럿이면 표의 하위 항목(베이 종류)과 맞는 행을 쓰고, 고르지 못하면 "확인 필요"로 두어야 한다(SHALL).

#### Scenario: 고를 수 없는 행
- **WHEN** 피더용·인입용 차단기 행이 모두 맞고 하위 항목으로 구분되지 않으면
- **THEN** 후보는 비어 있고 상태는 확인 필요이다
