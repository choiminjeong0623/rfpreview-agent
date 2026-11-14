"""db/migrations/*.sql 을 번호 순서대로 한 번씩만 적용한다."""

from pathlib import Path

import psycopg

LEDGER_DDL = """
CREATE TABLE IF NOT EXISTS schema_migration (
  version     VARCHAR(100) PRIMARY KEY,
  applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


def pending(conn: psycopg.Connection, migrations_dir: Path) -> list[Path]:
    applied = {row[0] for row in conn.execute("SELECT version FROM schema_migration")}
    return [p for p in sorted(migrations_dir.glob("*.sql")) if p.stem not in applied]


def migrate(conn: psycopg.Connection, migrations_dir: Path) -> list[str]:
    conn.execute(LEDGER_DDL)
    todo = pending(conn, migrations_dir)
    # 위 조회로 열린 암묵 트랜잭션을 닫아야 아래 transaction()이 저장점이 아닌 진짜 커밋이 된다.
    conn.commit()
    done = []
    for path in todo:
        # 파일 하나는 한 트랜잭션. 실패하면 그 파일은 통째로 되돌린다.
        with conn.transaction():
            conn.execute(path.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO schema_migration (version) VALUES (%s)", (path.stem,))
        done.append(path.stem)
    # 흐름 저장소 표(LangGraph checkpoint)는 라이브러리 자체 마이그레이션으로 만든다
    from rfp_agent.pipeline.graph_flow import setup_checkpoints

    setup_checkpoints(conn)
    return done
