"""검토 실행 대기열 (add-run-queue, FR-20·NFR-11·NFR-12).

등록·다시 시도·문서 추가·단계부터 다시는 작업(run_job)만 넣고, 처리기가 들어온 순서대로
`FOR UPDATE SKIP LOCKED`로 꺼낸다. 작업을 넣을 때마다 새 실행 토큰을 검토에 적어, 옛 실행은 다음
진행 기록 때 소유권을 잃고 스스로 멈춘다(run.check_cancel). 순서·분기는 코드가 정한다(CR-01).

처리기 방식(RFP_RUN_MODE=worker)은 `rfp-worker`가, 웹 서버 안 방식(inline, 기본)은 API 백그라운드
작업이 `drain`으로 같은 규칙(동시 실행 수·토큰·살아 있음)을 지켜 꺼낸다.
"""

import logging
import os
import socket
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from rfp_agent.config import get_settings
from rfp_agent.db.connection import connect

log = logging.getLogger(__name__)

HEARTBEAT_SECONDS = 30          # 살아 있음 기록 간격 [제안]
OWNERSHIP_SECONDS = 180         # 살아 있음이 이만큼 끊기면 다시 넣는다 [제안]
MAX_REQUEUE = 2                 # 다시 넣기 한도 [제안]
POLL_SECONDS = 2                # 처리기가 대기열을 보는 간격
CLAIM_LOCK = 72017              # 꺼내기를 한 줄로 세우는 advisory lock 번호
STALLED = "처리 실패 — 처리기가 멈춤: 살아 있음 기록이 끊겨 다시 넣기 한도를 넘었습니다."
KINDS = ("START", "RETRY", "ADD_DOCS", "REWIND")


@dataclass
class Job:
    job_id: int
    run_id: int
    kind: str
    payload: dict
    token: str


def worker_name() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{threading.get_ident()}"


def enqueue(conn: psycopg.Connection, run_id: int, kind: str, paths: list[Path],
            choices: dict | None = None, rewind: str | None = None) -> int:
    """작업을 넣는다. 새 토큰을 검토에 적어 지금 돌고 있는 옛 실행의 소유권을 빼앗는다."""
    assert kind in KINDS
    token = str(uuid.uuid4())
    with conn.transaction():
        conn.execute("UPDATE run_job SET status = 'DROPPED', finished_at = now() "
                     "WHERE run_id = %s AND status = 'QUEUED'", (run_id,))
        conn.execute(
            "UPDATE review_run SET run_token = %s, graph_state = graph_state || "
            "jsonb_build_object('step', 'queued', 'detail', NULL, 'updated_at', now()) "
            "WHERE run_id = %s", (token, run_id))
        job_id = conn.execute(
            """INSERT INTO run_job (run_id, kind, payload, token) VALUES (%s, %s, %s, %s)
               RETURNING job_id""",
            (run_id, kind, Jsonb({"paths": [str(p) for p in paths], "choices": choices or {},
                                  "rewind": rewind}), token)).fetchone()[0]
    return job_id


def claim(conn: psycopg.Connection, worker: str, limit: int) -> Job | None:
    """동시 실행 수가 남아 있으면 가장 오래된 작업 하나를 꺼낸다. 토큰을 잃은 작업은 버린다."""
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (CLAIM_LOCK,))
        running = conn.execute("SELECT count(*) FROM run_job WHERE status = 'RUNNING'"
                               ).fetchone()[0]
        if running >= limit:
            return None
        while True:
            row = conn.execute(
                """SELECT j.job_id, j.run_id, j.kind, j.payload, j.token::text,
                          j.token IS NOT DISTINCT FROM r.run_token
                   FROM run_job j JOIN review_run r USING (run_id)
                   WHERE j.status = 'QUEUED' ORDER BY j.job_id
                   LIMIT 1 FOR UPDATE OF j SKIP LOCKED""").fetchone()
            if row is None:
                return None
            job_id, run_id, kind, payload, token, owned = row
            if not owned:
                conn.execute("UPDATE run_job SET status = 'DROPPED', finished_at = now() "
                             "WHERE job_id = %s", (job_id,))
                continue
            conn.execute(
                """UPDATE run_job SET status = 'RUNNING', worker = %s, started_at = now(),
                          heartbeat_at = now() WHERE job_id = %s""", (worker, job_id))
            return Job(job_id, run_id, kind, payload, token)


def beat(conn: psycopg.Connection, job_id: int | None, worker: str | None) -> None:
    if job_id is not None:
        conn.execute("UPDATE run_job SET heartbeat_at = now() WHERE job_id = %s", (job_id,))
    if worker is not None:
        conn.execute(
            """INSERT INTO run_worker (worker_id, heartbeat_at) VALUES (%s, now())
               ON CONFLICT (worker_id) DO UPDATE SET heartbeat_at = now()""", (worker,))


class Heartbeat:
    """작업을 도는 동안 정해진 간격으로 살아 있음을 적는 스레드 (자동 커밋 연결)."""

    def __init__(self, job_id: int, every: float = HEARTBEAT_SECONDS):
        self.job_id, self.every = job_id, every
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        try:
            with connect() as conn:
                conn.autocommit = True
                while not self._stop.wait(self.every):
                    beat(conn, self.job_id, None)
        except psycopg.Error as exc:
            log.warning("살아 있음 기록 실패 (작업 %s): %s", self.job_id, exc)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()


def finish(conn: psycopg.Connection, job: Job, result: str, error: str | None = None) -> None:
    status = {"ENGINEER_REVIEW": "DONE", "SUPERSEDED": "DROPPED"}.get(result, "FAILED")
    conn.execute("UPDATE run_job SET status = %s, finished_at = now(), error = %s "
                 "WHERE job_id = %s AND status = 'RUNNING'", (status, error, job.job_id))
    conn.commit()


def run(job: Job) -> str:
    """작업 하나를 끝까지 돌린다. 실행 소유권은 job.token."""
    from rfp_agent.pipeline.service import run_to_end

    payload = job.payload
    with Heartbeat(job.job_id):
        try:
            result = run_to_end(job.run_id, [Path(p) for p in payload["paths"]],
                                payload.get("choices") or {}, payload.get("rewind"),
                                token=job.token)
            error = None
        except Exception as exc:                        # run_to_end가 못 잡은 오류 (DB 끊김 등)
            log.exception("작업 %s 실패", job.job_id)
            result, error = "FAILED", str(exc)[:500]
    with connect() as conn:
        finish(conn, job, result, error)
        _send_langfuse(conn, job)
    return result


def _send_langfuse(conn: psycopg.Connection, job: Job) -> None:
    """작업이 끝나면 AI 호출 기록을 Langfuse로 (add-langfuse-trace-push). 실패해도 그대로."""
    from rfp_agent.pipeline import langfuse_ops

    try:
        langfuse_ops.send_run(conn, job.run_id, job.token)
    except Exception:                                   # 보내기는 검토 결과와 상관없다
        log.exception("작업 %s의 AI 호출 기록을 Langfuse로 보내지 못함", job.job_id)


def reclaim(conn: psycopg.Connection, now_sql: str = "now()") -> list[int]:
    """살아 있음이 소유권 시간 넘게 끊긴 작업을 새 토큰으로 다시 넣는다. 한도를 넘으면 실패."""
    requeued = []
    with conn.transaction():
        stale = conn.execute(
            f"""SELECT job_id, run_id, kind, payload, attempts FROM run_job
                WHERE status = 'RUNNING'
                  AND heartbeat_at < {now_sql} - make_interval(secs => %s)
                FOR UPDATE SKIP LOCKED""", (OWNERSHIP_SECONDS,)).fetchall()
        for job_id, run_id, kind, payload, attempts in stale:
            conn.execute("UPDATE run_job SET status = 'FAILED', finished_at = now(), "
                         "error = '살아 있음 끊김' WHERE job_id = %s", (job_id,))
            if attempts < MAX_REQUEUE:
                token = str(uuid.uuid4())
                conn.execute("UPDATE review_run SET run_token = %s WHERE run_id = %s",
                             (token, run_id))
                new_id = conn.execute(
                    """INSERT INTO run_job (run_id, kind, payload, token, attempts)
                       VALUES (%s, %s, %s, %s, %s) RETURNING job_id""",
                    (run_id, kind, Jsonb(payload), token, attempts + 1)).fetchone()[0]
                requeued.append(new_id)
                log.warning("작업 %s 살아 있음 끊김 → 작업 %s로 다시 넣음", job_id, new_id)
            else:
                conn.execute(
                    """UPDATE review_run SET stage = 'FAILED', error_message = %s,
                              failed_step = graph_state->>'step', finished_at = now(),
                              run_token = NULL
                       WHERE run_id = %s AND stage = 'PROCESSING'""", (STALLED, run_id))
    return requeued


def drain(limit: int | None = None) -> int:
    """웹 서버 안 방식: 꺼낼 수 있는 작업이 없을 때까지 꺼내 돌린다. 돌린 수를 돌려준다."""
    limit = limit or get_settings().rfp_run_workers
    worker = worker_name()
    done = 0
    while True:
        with connect() as conn:
            reclaim(conn)
            job = claim(conn, worker, limit)
        if job is None:
            return done
        run(job)
        done += 1


def queue_position(conn: psycopg.Connection, run_id: int) -> int | None:
    """대기 중이면 몇 번째인지 (1부터). 꺼냈거나 작업이 없으면 None."""
    row = conn.execute(
        """SELECT (SELECT count(*) FROM run_job q WHERE q.status = 'QUEUED'
                     AND q.job_id <= j.job_id)
           FROM run_job j WHERE j.run_id = %s AND j.status = 'QUEUED'
           ORDER BY j.job_id DESC LIMIT 1""", (run_id,)).fetchone()
    return row[0] if row else None


def status(conn: psycopg.Connection) -> dict:
    """상태 점검: 실행 방식, 살아 있는 처리기 수, 대기 작업 수."""
    alive, queued = conn.execute(
        """SELECT (SELECT count(*) FROM run_worker
                    WHERE heartbeat_at > now() - make_interval(secs => %s)),
                  (SELECT count(*) FROM run_job WHERE status = 'QUEUED')""",
        (OWNERSHIP_SECONDS,)).fetchone()
    return {"run_mode": get_settings().rfp_run_mode, "workers_alive": alive,
            "jobs_queued": queued}


def serve() -> None:
    """`rfp-worker`: 처리기 프로세스. 동시 실행 수만큼 스레드가 대기열을 본다."""
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    limit = settings.rfp_run_workers
    host = f"{socket.gethostname()}:{os.getpid()}"
    stop = threading.Event()

    def loop(n: int) -> None:
        worker = f"{host}:{n}"
        while not stop.is_set():
            try:
                with connect() as conn:
                    conn.autocommit = False
                    beat(conn, None, worker)
                    conn.commit()
                    reclaim(conn)
                    job = claim(conn, worker, limit)
                if job is None:
                    stop.wait(POLL_SECONDS)
                    continue
                log.info("처리기 %s: 작업 %s (검토 %s, %s)", worker, job.job_id, job.run_id,
                         job.kind)
                run(job)
            except psycopg.Error as exc:
                log.warning("처리기 %s 대기열 오류: %s", worker, exc)
                stop.wait(POLL_SECONDS)

    threads = [threading.Thread(target=loop, args=(n,), daemon=True) for n in range(limit)]
    for t in threads:
        t.start()
    log.info("처리기 시작: 동시 실행 %s", limit)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        stop.set()


def main() -> None:
    serve()
