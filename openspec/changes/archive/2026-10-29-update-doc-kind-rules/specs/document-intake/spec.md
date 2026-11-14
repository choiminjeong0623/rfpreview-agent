## MODIFIED Requirements

### Requirement: 문서 분류
시스템은 docx 파일마다 파일 번호, 묶음(A/B/C/D), 문서 종류, 사업 ID, 언어, 주 규격 체계, 판정 대상 여부를 정해야 한다(SHALL). 파일명·첫 장 표현으로 코드가 1차 판별하고 AI는 보조하며, 둘이 다르면 "확인 필요"로 표시해야 한다(SHALL). 문서 종류를 정하는 파일명·첫 장 표현은 적재된 문서 종류 규칙 사전을 순서대로 쓴다(SHALL). 판정 대상은 묶음 A·B뿐이다(CR-09).

#### Scenario: 입찰 서식
- **WHEN** 파일 1(RFP01 Bidding Forms)을 분류하면
- **THEN** 묶음 A, 입찰 서식, 판정 대상, 주 규격 체계 IEC이다

#### Scenario: 판정 대상이 아닌 미국 사양서
- **WHEN** 파일 13(RFP13 Medium-Voltage Switchgear)을 분류하면
- **THEN** 묶음 C, 요구 사양, 판정 대상 아님, 주 규격 체계 IEEE·UL이다

#### Scenario: 이미지만 있는 문서
- **WHEN** 이미지만 있는 파일 8을 분류하면
- **THEN** "판독 불가"로 두고 이후 단계를 건너뛴다

#### Scenario: 사전 순서대로 문서 종류 정하기
- **WHEN** 파일 이름이 "Testing Specification"인 문서를 분류하면
- **THEN** 사전에서 먼저 맞는 시험 사양서 줄(파일 이름 "testing")이 이겨 문서 종류는 시험 사양서다

#### Scenario: 사전에 없는 표현
- **WHEN** 파일 이름과 첫 장 어디에도 사전 표현이 없는 문서를 분류하면
- **THEN** 문서 종류는 "종류 모름"이고 "확인 필요"다
