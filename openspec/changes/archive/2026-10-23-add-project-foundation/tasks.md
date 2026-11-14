# Tasks

## 1. 저장소 뼈대

- [x] 1.1 폴더 구조, .gitignore(data/private 제외), .env.example
- [x] 1.2 backend: uv 프로젝트, 설정(pydantic-settings), ruff·pytest
- [x] 1.3 frontend: Vite React TS, /api 프록시, 상태 화면
- [x] 1.4 Docker Compose (db, backend, frontend)

## 2. 스키마

- [x] 2.1 schema_v1.sql을 0001로, 고정 코드표와 SOURCE 방향을 0002로
- [x] 2.2 마이그레이션 실행기와 `rfp-db migrate`
- [x] 2.3 테스트: 처음 적용, 두 번째 실행, 유형 7종

## 3. 기준 데이터 적재

- [x] 3.1 규칙 사전 4종 적재와 `rfp-db seed-rules`
- [x] 3.2 제품표·손실값 적재와 `rfp-db seed-products`
- [x] 3.3 테스트: 반복 적재, 시간 조건, 회사 고정값, 모르는 방향, 뒤 파일 우선, 손실값, 설계 사례 카드

## 4. 상태 점검

- [x] 4.1 `/api/health`
- [x] 4.2 테스트: 정상, DB 장애

## 5. 마무리

- [x] 5.1 README, CI (ruff, pytest + PostgreSQL, 프런트 빌드)
- [x] 5.2 openspec validate --strict 통과와 archive
