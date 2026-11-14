# Spec Delta

## ADDED Requirements

### Requirement: 팀 가정 표시
시스템은 팀 가정 값이 들어간 모든 결과에 "팀 가정" 표시를 붙여야 한다(SHALL, CR-06).

#### Scenario: 가정 값이 섞인 결과
- **WHEN** 결과 계산에 팀 가정 값이 하나라도 쓰이면
- **THEN** 그 결과는 팀 가정으로 표시된다
