# Design

## Context

schema_v1.sql은 PostgreSQL 16 기준 초안이고 DB 담당 검토 전이다. 사전 초안 CSV는 한국어 머리글과 기호(≥, 작성, 포함 …)로 되어 있어 DB의 코드값(GE, FILL, IN …)으로 바꿔야 한다. 팀은 곧 4명(PM·DB / AI / BE / FE)으로 늘어난다.

## Goals / Non-Goals

**Goals:**
- `docker compose up` 한 번 또는 `rfp-db setup` 한 번으로 누구나 같은 DB 상태를 얻는다.
- 스키마가 바뀌면 새 번호의 SQL 파일만 추가하면 된다.
- 사전 CSV에 코드로 못 바꾸는 값이 있으면 조용히 넘어가지 않고 멈춘다.

**Non-Goals:**
- 문서 처리·판정 등 기능 코드 (다음 change들).
- 칸 이름 사전·유형 규칙표·사업 묶음 표 작성 (명세서 8장 "신규 작성 필요").
- 비교 방향 사전의 "강점 방향" 칸 (FR-07 change에서 사전과 함께 추가).

## Decisions

- **마이그레이션은 순수 SQL + 작은 실행기.** Alembic 대신 `db/migrations/NNNN_*.sql`을 `schema_migration` 표에 기록하며 한 파일씩 한 트랜잭션으로 적용한다. DB 담당이 SQL을 직접 읽고 고칠 수 있고, schema_v1 파일을 그대로 0001로 쓸 수 있다.
- **사전 적재는 덮어쓰기.** compare_rule·risk_expression·item_pm_mapping은 지우고 다시 넣고, item_key·company_fixed_value·product_master는 키 기준 upsert. 사전 판이 바뀌어도 결과가 파일 내용과 같다.
- **방향 기호 매핑은 표 하나(`DIRECTION_CODES`).** 표에 없는 기호가 나오면 `SeedError`로 멈춘다.
- **제품표 순서:** 입력용 → TRF v2 순으로 읽고 같은 코드는 뒤 파일이 이긴다(TRF-HV). 설계 사례 카드는 설명이 `[설계 사례 카드`로 시작하는 행으로 판별해 `is_design_card`를 켠다. `lifecycle_status`가 빈 행은 `UNKNOWN`.
- **데이터 위치:** 팀이 만든 사전·제품표는 `data/seed/`에 커밋(비공개 저장소). 고객사 RFP 원본은 `data/private/`(git 제외)에 두고 Compose가 읽기 전용으로 붙인다.

## Risks / Trade-offs

- `SOURCE` 방향 추가는 schema_v1 변경이다 → 0002에 따로 두어 DB 담당이 되돌리기 쉽게 했다.
- 위험 표현 사전에서 조건이 빈 4줄은 `(조건 미정)`으로 들어간다 → FR-06 change에서 팀이 조건을 정해야 한다.
- 변압기 손실값은 아직 CSV에 없다 → 손실 칸은 비어 있고, FR-13은 팀 가정 값이 들어온 뒤 동작한다.
