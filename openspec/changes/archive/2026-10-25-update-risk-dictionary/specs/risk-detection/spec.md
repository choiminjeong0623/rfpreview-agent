## MODIFIED Requirements

### Requirement: 범위 모호 후보와 상태
시스템은 공급 범위 문장 안의 열린 표현을 범위 모호 후보로 내야 한다(SHALL). 모든 위험 조건은 후보로 시작하고 사람이 확정하거나 정상으로 닫는다(CR-08).

#### Scenario: including but not limited to
- **WHEN** 공급 범위 문장에 "including but not limited to"가 있으면
- **THEN** 범위 모호 후보 1건이 상태 "후보"로 나온다

#### Scenario: including 없는 but not limited to
- **WHEN** 파일 2 369행처럼 공급 범위 절의 "The Scope of Work includes design, supply, … as summarized below but not limited to;"를 검사하면
- **THEN** 범위 모호 후보 1건이 상태 "후보"로 나온다

#### Scenario: 공급 범위가 아닌 절의 but not limited to
- **WHEN** 제출 서류나 보고서 절 안의 "but not limited to"를 검사하면
- **THEN** 후보가 아니다

#### Scenario: 겹치는 열린 표현
- **WHEN** 한 공급 범위 문장이 "including but not limited to"와 "but not limited to"에 모두 걸리면
- **THEN** 범위 모호 후보는 1건이다
