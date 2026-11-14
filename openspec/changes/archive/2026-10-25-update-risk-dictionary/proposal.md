# Proposal

## Why

위험 표현 사전에는 "including but not limited to"만 있어서, 앞에 "including"이 없는 열린 표현을 놓친다.
파일 2(RFP02 Employers Requirement Substation) 369행 "The Scope of Work includes design, supply, …
as summarized below but not limited to;"가 그 예다. 같은 모양의 공급 범위 문장이 403·435·460·485행에도 있다.
명세서 FR-06 ④ "범위 모호: 공급 범위 문장 안의 열린 표현"에 해당하지만 지금은 후보로 나오지 않는다.

## What Changes

- 위험 표현 사전(`data/seed/risk_expressions.csv`)에 "but not limited to"(영어, 범위 모호, 공급 범위 문장 안에 있을 때)를 더한다.
- "including but not limited to" 문장은 두 표현에 모두 걸리지만, 같은 조항·같은 종류는 이미 후보 하나로 모으므로 후보 수는 그대로 1건이다.
- 조건(공급 범위 절 안)은 그대로라서, 일일 보고서·제출 서류처럼 공급 범위가 아닌 절의 "but not limited to"는 후보가 아니다.

## Capabilities

### Modified Capabilities
- `risk-detection`: 범위 모호 후보에 "but not limited to" 시나리오와, 겹치는 표현이어도 후보 1건인 시나리오를 더한다.

## Impact

- 사전 9개 → 10개. 코드와 스키마는 바꾸지 않는다 (시드를 다시 넣으면 반영).
- 파일 2의 공급 범위 절에서 범위 모호 후보가 늘 수 있다. 실제 건수는 화면에서 확인한다.
