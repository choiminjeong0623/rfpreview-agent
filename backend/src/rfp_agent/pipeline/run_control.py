"""검토 취소와 다시 시도 (add-run-control).

취소는 요청만 적는다. 처리 흐름은 진행을 기록할 때 요청을 보고 스스로 멈춘다(run.check_cancel).
다시 시도는 처음 시작할 때 남긴 파일·분류로 같은 검토를 처음부터 다시 돌린다.
이미 처리한 문서는 다시 쓰고(NFR-05) 나머지 결과는 단계마다 지우고 다시 만든다.
"""

from pathlib import Path

import psycopg

from rfp_agent.pipeline.numbers import josa
from rfp_agent.pipeline.review import ReviewError

STALL_MINUTES = 10          # 화면의 "10분 넘게 진행이 없습니다"와 같은 기준


def _run(conn: psycopg.Connection, run_id: int) -> tuple:
    row = conn.execute(
        """SELECT stage, graph_state->>'step',
                  now() - COALESCE((graph_state->>'updated_at')::timestamptz, started_at)
                      > make_interval(mins => %s),
                  graph_state->'inputs'
           FROM review_run WHERE run_id = %s FOR UPDATE""", (STALL_MINUTES, run_id)).fetchone()
    if row is None:
        raise ReviewError(404, f"검토 실행 {run_id}이(가) 없습니다.")
    return row


def request_cancel(conn: psycopg.Connection, run_id: int, actor_id: int | None) -> None:
    """처리 중인 검토에 취소를 요청한다. 진행이 10분 넘게 없으면 바로 멈춘 것으로 표시한다."""
    with conn.transaction():
        stage, step, stalled, _ = _run(conn, run_id)
        if stage != "PROCESSING":
            raise ReviewError(409, "처리 중인 검토만 취소할 수 있습니다.")
        conn.execute(
            """UPDATE review_run SET cancel_requested_at = now(), cancel_requested_by = %s
               WHERE run_id = %s""", (actor_id, run_id))
        if stalled:
            # 처리 흐름이 살아 있지 않다고 본다(백엔드가 꺼짐 등).
            # 살아 있으면 다음 기록 때 스스로 멈춘다
            who = conn.execute("SELECT user_name FROM app_user WHERE user_id = %s",
                               (actor_id,)).fetchone()
            name = who[0] if who else "사용자"
            conn.execute(
                """UPDATE review_run SET stage = 'FAILED', failed_step = %s, error_message = %s,
                          finished_at = now() WHERE run_id = %s""",
                (step, josa(f"진행이 {STALL_MINUTES}분 넘게 멈춰 {name}이(가) "
                            "분석을 취소했습니다."), run_id))


def prepare_retry(conn: psycopg.Connection, run_id: int,
                  actor_id: int | None) -> tuple[list[Path], dict[str, dict]]:
    """실패·취소한 검토를 다시 처리 중으로 돌리고 처음 입력(파일 경로, 사람 분류)을 돌려준다."""
    with conn.transaction():
        stage, _, _, inputs = _run(conn, run_id)
        if stage != "FAILED":
            raise ReviewError(409,
                              "처리에 실패했거나 취소한 검토만 다시 시도할 수 있습니다.")
        if not inputs or not inputs.get("paths"):
            raise ReviewError(409, "이 검토는 다시 돌릴 파일 정보가 없습니다. "
                                   "검토를 다시 등록해 주세요.")
        paths = [Path(p) for p in inputs["paths"]]
        missing = [p.name for p in paths if not p.exists()]
        if missing:
            raise ReviewError(409, f"올린 파일을 찾을 수 없습니다({', '.join(missing)}). "
                                   "검토를 다시 등록해 주세요.")
        conn.execute(
            """UPDATE review_run SET stage = 'PROCESSING', failed_step = NULL, error_message = NULL,
                      finished_at = NULL, cancel_requested_at = NULL, cancel_requested_by = NULL,
                      retry_count = retry_count + 1,
                      graph_state = graph_state || jsonb_build_object(
                          'step', 'created', 'detail', NULL, 'updated_at', now(),
                          'retried_by', %s::int)
               WHERE run_id = %s""", (actor_id, run_id))
    return paths, inputs.get("choices") or {}
