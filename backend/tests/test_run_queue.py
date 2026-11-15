"""검토 실행 대기열 (change add-run-queue, FR-20·NFR-11·NFR-12).

명세 review-run "검토 실행 대기열"·"실행 소유권"·"처리기 살아 있음과 다시 넣기"·
"중복 등록 방지와 업로드 상한"·"처리기 상태 점검"의 Scenario. AI는 끈다(RFP_AI_MODE=off).
"""

import json

import psycopg
import pytest

from rfp_agent.config import get_settings
from rfp_agent.pipeline import ocr, queries, run_control, run_queue
from rfp_agent.pipeline.run import RunContext, create_run, execute_run
from tests.test_unread_pages import build_pdf

VERSION = "test-dict-v1"


@pytest.fixture
def env(db, db_url, monkeypatch):
    """대기열·처리기가 여는 연결이 시험 DB를 보게 하고 AI는 끈다."""
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("RFP_AI_MODE", "off")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    get_settings.cache_clear()
    yield monkeypatch
    get_settings.cache_clear()


def client_for(env, mode: str = "inline", **settings):
    from fastapi.testclient import TestClient

    from rfp_agent.api.main import app

    env.setenv("RFP_RUN_MODE", mode)
    for key, value in settings.items():
        env.setenv(key, str(value))
    get_settings.cache_clear()
    return TestClient(app)


def upload(client, path, **extra):
    data = {"due_date": "2026-12-01",
            "choices": json.dumps({path.name: {"bundle": "B"}})} | extra
    return client.post("/api/runs", files=[("files", (path.name, path.read_bytes()))], data=data)


def count(conn, table, where="TRUE"):
    conn.commit()
    return conn.execute(f"SELECT count(*) FROM {table} WHERE {where}").fetchone()[0]


def queued_run(conn, path) -> int:
    run_id = create_run(conn, VERSION, None)
    run_queue.enqueue(conn, run_id, "START", [path], {path.name: {"bundle": "B"}})
    return run_id


def stage(conn, run_id) -> str:
    conn.commit()
    return conn.execute("SELECT stage FROM review_run WHERE run_id = %s", (run_id,)).fetchone()[0]


# ── 검토 실행 대기열 ───────────────────────────────────────────────────

def test_register_does_not_wait_for_ocr(env, db, tmp_path, monkeypatch):
    """Scenario: 스캔 PDF 등록은 OCR을 기다리지 않음 — 응답에 OCR 없음, 처리 중·대기 중 1번째."""
    def no_ocr(*_):
        raise AssertionError("등록 요청이 OCR을 했다")
    monkeypatch.setattr(ocr, "read", no_ocr)
    monkeypatch.setattr(ocr, "read_lines", no_ocr)
    client = client_for(env, "worker")
    path = build_pdf(tmp_path / "scan_mid.pdf", ["text", "scan", "text"])
    res = upload(client, path)
    assert res.status_code == 202, res.text
    body = res.json()
    assert (body["stage"], body["queue_position"]) == ("PROCESSING", 1)
    assert count(db, "run_job", "status = 'QUEUED'") == 1


def test_two_workers_three_runs(env, db, spec):
    """Scenario: 동시 실행 수 2에 등록 3건 — 2건 처리 중, 1건 대기 중 1번째, 하나가 끝나면 꺼냄."""
    runs = [queued_run(db, spec) for _ in range(3)]
    first = run_queue.claim(db, "w1", 2)
    second = run_queue.claim(db, "w2", 2)
    assert [first.run_id, second.run_id] == runs[:2]
    assert run_queue.claim(db, "w3", 2) is None
    assert run_queue.queue_position(db, runs[2]) == 1
    assert queries.run_summary(db, runs[2])["queue_position"] == 1
    run_queue.finish(db, first, "ENGINEER_REVIEW")
    third = run_queue.claim(db, "w3", 2)
    assert third.run_id == runs[2] and run_queue.queue_position(db, runs[2]) is None


def judgments(conn, run_id):
    conn.commit()
    return sorted(conn.execute(
        "SELECT item_key, result, required_value FROM judgment WHERE run_id = %s AND is_current",
        (run_id,)).fetchall(), key=repr)


def test_same_result_with_one_or_two_workers(env, db, spec):
    """Scenario: 동시 실행 수 1과 2의 결과 — 요구사항과 판정이 같다."""
    one = queued_run(db, spec)
    assert run_queue.drain(1) == 1
    two = queued_run(db, spec)
    assert run_queue.drain(2) == 1
    assert stage(db, one) == stage(db, two) == "ENGINEER_REVIEW"
    assert judgments(db, one) == judgments(db, two) and judgments(db, one)
    assert queries.run_summary(db, one)["requirements"] == \
        queries.run_summary(db, two)["requirements"]


# ── 실행 소유권 ────────────────────────────────────────────────────────

def test_cancel_then_retry_runs_once(env, db, db_url, spec):
    """Scenario: 취소 직후 다시 시도 — 옛 실행은 결과를 쓰지 않고 멈추고, 새 실행 하나만 쓴다."""
    run_id = queued_run(db, spec)
    old = run_queue.claim(db, "old", 2)
    actor = db.execute("SELECT min(user_id) FROM app_user WHERE role = 'ENGINEER'").fetchone()[0]

    def retry_on_first_report(rid, detail):
        if retry_on_first_report.done:
            return
        retry_on_first_report.done = True
        # 화면에서 취소하고 (멈춘 것으로 보여) 바로 다시 시도한 것처럼: 새 작업, 새 토큰
        with psycopg.connect(db_url, autocommit=True) as other:
            run_control.request_cancel(other, rid, actor)
            other.execute("UPDATE review_run SET stage = 'FAILED' WHERE run_id = %s", (rid,))
            paths, choices = run_control.prepare_retry(other, rid, actor)
            run_queue.enqueue(other, rid, "RETRY", paths, choices)
    retry_on_first_report.done = False

    ctx = RunContext(db, VERSION, None, None, retry_on_first_report, token=old.token)
    assert execute_run(ctx, run_id, [spec], {spec.name: {"bundle": "B"}}) == "SUPERSEDED"
    assert stage(db, run_id) == "PROCESSING"                     # 옛 실행은 아무것도 쓰지 않음
    assert count(db, "document") == 0
    run_queue.finish(db, old, "SUPERSEDED")
    assert run_queue.drain(2) == 1                               # 새 작업 하나만 돈다
    assert stage(db, run_id) == "ENGINEER_REVIEW"
    assert count(db, "run_job", "status = 'DONE'") == 1


# ── 살아 있음과 다시 넣기 ──────────────────────────────────────────────

def stale(conn, job_id):
    conn.execute("UPDATE run_job SET heartbeat_at = now() - interval '10 minutes' "
                 "WHERE job_id = %s", (job_id,))
    conn.commit()


def test_worker_killed_then_restarted(env, db, spec):
    """Scenario: 처리기를 강제로 끈 뒤 다시 켬 — 다시 넣어 이어서 처리하고 담당자 확인에서 멈춘다."""
    run_id = queued_run(db, spec)
    job = run_queue.claim(db, "dead", 2)
    stale(db, job.job_id)                                        # 살아 있음이 끊김
    [again] = run_queue.reclaim(db)
    row = db.execute("SELECT attempts, token::text FROM run_job WHERE job_id = %s",
                     (again,)).fetchone()
    assert row[0] == 1 and row[1] != job.token
    assert run_queue.drain(2) == 1
    assert stage(db, run_id) == "ENGINEER_REVIEW"


def test_requeue_limit(env, db, spec):
    """Scenario: 다시 넣기 한도 — 2번 뒤에도 끊기면 처리 실패, "처리기가 멈춤"."""
    run_id = queued_run(db, spec)
    for _ in range(run_queue.MAX_REQUEUE + 1):
        job = run_queue.claim(db, "dead", 2)
        stale(db, job.job_id)
        run_queue.reclaim(db)
    s = queries.run_summary(db, run_id)
    assert s["stage"] == "FAILED" and "처리기가 멈춤" in s["error_message"]
    assert run_queue.claim(db, "w", 2) is None


def test_cancel_queued_run(env, db, spec):
    """Scenario: 대기 중 검토 취소 — 실행 없이 바로 취소, 작업은 꺼내지지 않는다."""
    run_id = queued_run(db, spec)
    run_control.request_cancel(db, run_id, None)
    db.commit()
    s = queries.run_summary(db, run_id)
    assert s["stage"] == "FAILED" and s["error_message"].endswith("분석을 취소했습니다.")
    assert run_queue.claim(db, "w", 2) is None
    assert count(db, "run_job", "status = 'DROPPED'") == 1


# ── 중복 등록 방지와 업로드 상한 ───────────────────────────────────────

def test_same_request_key_twice(env, db, spec):
    """Scenario: 같은 요청 키로 두 번 등록 — 검토 1개, 두 응답의 검토 번호가 같다."""
    client = client_for(env, "worker")
    first = upload(client, spec, request_key="reg-123")
    second = upload(client, spec, request_key="reg-123")
    assert first.status_code == second.status_code == 202, second.text
    assert first.json()["run_id"] == second.json()["run_id"]
    assert count(db, "review_run") == 1


def test_upload_too_large(env, db, spec):
    """Scenario: 파일 크기 상한 초과 — 400과 상한 안내, 검토 없음."""
    client = client_for(env, "worker", RFP_UPLOAD_MAX_MB=0)
    res = upload(client, spec)
    assert res.status_code == 400 and "MB까지 올릴 수 있습니다" in res.json()["detail"]
    assert count(db, "review_run") == 0


# ── 처리기 상태 점검 ───────────────────────────────────────────────────

def test_no_worker_alive(env, db, spec):
    """Scenario: 처리기 0개 — 검토는 대기 중, 상태 점검에 처리기 0·대기 작업 1."""
    client = client_for(env, "worker")
    assert upload(client, spec).json()["queue_position"] == 1
    health = client.get("/api/health").json()
    assert (health["run_mode"], health["workers_alive"], health["jobs_queued"]) == \
        ("WORKER", 0, 1)
