"""설정에서 사전 판·AI·txt 위치를 모아 검토 실행을 만들고 돌린다 (CLI와 API가 같이 쓴다)."""

from pathlib import Path

import psycopg

from rfp_agent.config import get_settings
from rfp_agent.db.connection import connect
from rfp_agent.db.seed import dict_version
from rfp_agent.llm.client import make_llm
from rfp_agent.pipeline.run import RunContext, create_run, execute_run, write_progress


def make_context(conn: psycopg.Connection) -> RunContext:
    settings = get_settings()
    txt_dir = settings.txt_dir if settings.txt_dir.exists() else None
    return RunContext(conn, dict_version(settings.seed_dir, conn),
                      make_llm(settings), txt_dir)


def start_run(conn: psycopg.Connection, started_by: int | None = None) -> int:
    ctx = make_context(conn)
    return create_run(conn, ctx.version, ctx.llm, started_by)


def run_to_end(run_id: int, paths: list[Path], choices: dict[str, dict] | None = None,
               rewind: str | None = None) -> str:
    """새 연결로 실행을 끝까지 돌린다 (API 백그라운드 작업용).

    세부 진행은 자동 커밋 연결 하나를 더 열어 바로 적는다 (처리 상태 화면).
    """
    with connect() as conn, connect() as side:
        side.autocommit = True
        ctx = make_context(conn)
        ctx.progress = write_progress(side)
        return execute_run(ctx, run_id, paths, choices, rewind)
