# Proposal

## Why

Must 기능(FR-01~10, 13, 14)을 만들려면 모든 기능이 같이 쓰는 DB 스키마, 규칙 사전, 제품표가 먼저 DB에 있어야 한다. 지금은 schema_v1.sql과 사전 초안 CSV가 문서로만 있어서, 팀원 네 명이 같은 상태에서 시작할 방법이 없다.

## What Changes

- 저장소 뼈대: `backend/`(FastAPI), `frontend/`(React·Vite·TS), `db/migrations/`, `data/seed/`, `data/private/`(git 제외), `docs/reference/`, `openspec/`.
- `db/migrations/0001_schema_v1.sql`(schema_v1 그대로)과 `0002_reference_codes.sql`(유형 7종, 승인 기준 AR-01·02·03·06·07·08, 칸 이름 사전 3줄, 비교 방향 `SOURCE` 추가)을 번호 순서로 한 번씩만 적용하는 명령.
- 규칙 사전 4종(항목 이름, 비교 방향, 위험 표현, 항목→product_master 연결표)과 제품표(입력용 59행 + TRF v2 35행 + 변압기 손실값)를 DB에 넣는 적재 명령. 같은 파일을 여러 번 넣어도 결과가 같다(CR-11).
- `/api/health`: API·DB·스키마 판·언어 모델 키 설정 여부를 알려 준다.
- Docker Compose로 db·backend·frontend를 한 번에 띄운다.

## Capabilities

### New Capabilities
- `reference-data`: 스키마 마이그레이션과 규칙 사전·제품표 적재. 이후 모든 기능이 읽는 기준 데이터의 내용과 규칙.
- `service-health`: 시스템 상태 점검 응답.

### Modified Capabilities

## Impact

- 새 의존성: FastAPI, uvicorn, pydantic-settings, psycopg 3 / React 19, Vite.
- schema_v1에서 바뀐 점은 `item_key.default_direction`과 `compare_rule.direction`에 `SOURCE`(요구값 기호를 따름)를 허용한 것 하나. 비교 방향 사전에 "원문 기호 따름" 줄이 있어서다. DB 담당 확인 필요.
- RFP 원본 docx는 저장소에 올리지 않는다(기획서 5-6).
