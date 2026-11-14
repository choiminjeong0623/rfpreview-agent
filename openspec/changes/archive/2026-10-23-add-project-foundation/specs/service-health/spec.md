# Spec Delta

## Purpose

운영자와 화면이 API, DB, 스키마 판, 언어 모델 설정 상태를 한 번에 확인하게 한다.

## ADDED Requirements

### Requirement: 상태 점검 응답
시스템은 `/api/health`에서 API 상태, DB 연결 상태, 마지막으로 적용된 스키마 판, 언어 모델 키 설정 여부를 돌려줘야 한다(SHALL). 키 값 자체는 돌려주지 않아야 한다(MUST NOT).

#### Scenario: 정상
- **WHEN** DB가 연결되고 마이그레이션이 적용된 상태에서 상태를 조회하면
- **THEN** status는 ok, database는 ok, schema_version은 0002_reference_codes이다

#### Scenario: DB 장애
- **WHEN** DB에 연결할 수 없는 상태에서 상태를 조회하면
- **THEN** 오류 대신 status는 degraded, database는 down으로 응답한다
