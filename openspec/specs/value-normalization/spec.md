# value-normalization Specification

## Purpose
문장·칸에 섞인 값을 숫자·기호·단위·조건으로 나눠 비교할 수 있는 모양으로 바꾼다. 코드만 하고 단위 환산은 하지 않는다 (FR-05, CR-10).

## Requirements

### Requirement: 칸 형태 판별
시스템은 요구값을 빈칸 / 숫자 / 계산식 / 규격 위임 / 문장 / 예·아니오로 나눠야 한다(SHALL). ×, /, √가 있으면 계산식, "As per"·"according to"는 규격 위임이다.

#### Scenario: 기호가 붙은 숫자
- **WHEN** 19번 "<0.5" / % 를 정리하면
- **THEN** 숫자 0.5, 기호 <, 단위 %이고 원문 "<0.5"가 보존된다

#### Scenario: 규격 위임
- **WHEN** "As per IEC:62271-100"을 정리하면
- **THEN** 형태는 규격 위임, 규격은 IEC 62271-100이고 판정은 "확인 필요"로 간다

### Requirement: 계산식은 코드가 계산한다
시스템은 ×, /, √, 괄호만 쓴 계산식을 코드로 계산해 숫자로 저장해야 한다(SHALL). 그 밖의 계산식은 "확인 필요"로 표시해야 한다(SHALL).

#### Scenario: 1.1 × 125/√3
- **WHEN** "1.1 x 125/√3"(kV)을 정리하면
- **THEN** 형태는 계산식, 결과는 약 79.4, 단위는 kV이다

### Requirement: 단위 환산 안 함
시스템은 원문 단위를 그대로 저장하고 서로 환산하지 않아야 한다(SHALL, CR-10). 단위가 없으면 "단위 확인 필요"로 표시해야 한다(SHALL).

#### Scenario: 화씨와 섭씨
- **WHEN** 파일 13의 "104 deg F (40 deg C)"를 정리하면
- **THEN** 104 °F와 40 ℃가 각각 원문 단위로 저장되고 서로 환산되지 않는다

### Requirement: 조건·표준 항목·적용 대상
시스템은 값에 붙은 조건(시간 1s·3s 등), 항목 이름 사전의 표준 항목키, 적용 대상(장비·부위), 근거 규격, 사업 ID를 함께 저장해야 한다(SHALL). 사전에 없는 이름은 표준 항목키를 비우고 원문 이름으로만 저장한다.

#### Scenario: 시간 조건
- **WHEN** TS-115-GIS 16번 "Rated short-time withstand current, (1 sec.)" 40 kA를 정리하면
- **THEN** 숫자 40, 단위 kA, 시간 조건 1초, 표준 항목키 short_time_current이다
