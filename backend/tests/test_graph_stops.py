"""흐름 안의 멈춤 지점과 이어서 다시 시도 (change update-graph-stops, C2).

명세 review-approval "흐름 안의 멈춤 지점"·"문서 추가는 흐름을 처음 단계로 되돌림",
review-run "검토 다시 시도"·"실행 기록의 이어서 시작한 단계"의 Scenario.
"""

import psycopg
import pytest
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row

from rfp_agent.pipeline import doc_add, graph_flow, queries, review, run_control
from rfp_agent.pipeline import run as run_mod
from rfp_agent.pipeline.review import ReviewError
from rfp_agent.pipeline.run import RunContext, build_graph, create_run, execute_run
from rfp_agent.pipeline.run_log import run_log
from tests.docx_factory import build_gis_spec

VERSION = "test-dict-v1"
COMMENT = "확인 끝, 상신합니다"


def ctx(conn):
    return RunContext(conn, VERSION, None, None)


def user(conn, role):
    return review.default_user(conn, role)


def stop(db_url, run_id):
    """새 연결·새 흐름 실행기로 멈춘 자리를 읽는다 (서버를 다시 켠 것과 같다)."""
    with psycopg.connect(db_url, autocommit=True, prepare_threshold=0,
                         row_factory=dict_row) as side, psycopg.connect(db_url) as conn:
        return graph_flow.stop_of(build_graph(ctx(conn), PostgresSaver(side)), run_id)


@pytest.fixture
def run(db, spec):
    run_id = create_run(db, VERSION, None)
    assert execute_run(ctx(db), run_id, [spec]) == "ENGINEER_REVIEW"
    return run_id


def submit(db, run_id):
    return review.finish_review(db, run_id, user(db, "APPROVER"), COMMENT, user(db, "ENGINEER"))


def stage(db, run_id):
    return queries.run_summary(db, run_id)["stage"]


def test_stops_at_engineer_review(db, db_url, run):
    """Scenario: 처리를 마치면 담당자 확인에서 멈춤."""
    assert stage(db, run) == "ENGINEER_REVIEW"
    assert stop(db_url, run) == "engineer_review"


def test_submit_moves_to_approval(db, db_url, run):
    """Scenario: 상신하면 승인 대기 자리로."""
    submit(db, run)
    assert stage(db, run) == "APPROVAL"
    assert stop(db_url, run) == "approval"


def test_reject_then_reopen(db, db_url, run):
    """Scenario: 반려 뒤 다시 확인 — 반려됨 자리를 거쳐 담당자 확인으로."""
    submit(db, run)
    review.decide(db, run, "REJECTED", "근거 보강 필요", user(db, "APPROVER"))
    assert stage(db, run) == "REJECTED" and stop(db_url, run) == "rejected"
    review.reopen(db, run, user(db, "ENGINEER"))
    assert stage(db, run) == "ENGINEER_REVIEW" and stop(db_url, run) == "engineer_review"
    submit(db, run)                                   # 다시 올릴 수 있다
    assert stop(db_url, run) == "approval"


def test_withdraw_returns_to_engineer_review(db, db_url, run):
    """Scenario: 상신 취소 — 흐름은 담당자 확인 자리로 돌아온다."""
    submit(db, run)
    review.withdraw(db, run, user(db, "ENGINEER"))
    assert stage(db, run) == "ENGINEER_REVIEW" and stop(db_url, run) == "engineer_review"


def test_approve_ends_flow(db, db_url, run):
    """Scenario: 승인하면 흐름이 끝남."""
    submit(db, run)
    review.decide(db, run, "APPROVED", None, user(db, "APPROVER"))
    assert stage(db, run) == "APPROVED"
    assert stop(db_url, run) == graph_flow.ENDED


def test_resume_after_restart(db, db_url, run):
    """Scenario: 서버를 다시 켜도 이어 감 — 새 연결에서 상신해도 같은 흐름이 이어진다."""
    with psycopg.connect(db_url) as fresh:
        submit(fresh, run)
        fresh.commit()
    assert stop(db_url, run) == "approval"


def test_rejected_action_keeps_stop(db, db_url, run):
    """Scenario: 거절된 동작은 자리를 바꾸지 않음 — 의견 없는 상신은 400, 흐름 그대로."""
    with pytest.raises(ReviewError) as err:
        review.finish_review(db, run, user(db, "APPROVER"), "", user(db, "ENGINEER"))
    assert err.value.status == 400
    assert stop(db_url, run) == "engineer_review" and stage(db, run) == "ENGINEER_REVIEW"


def test_old_run_without_flow(db, db_url, run):
    """Scenario: 흐름 기록이 없는 예전 검토 — 지금처럼 승인 대기가 된다."""
    for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
        db.execute(f"DELETE FROM {table} WHERE thread_id = %s", (f"run-{run}",))
    db.commit()
    assert stop(db_url, run) is graph_flow.NO_FLOW
    assert submit(db, run)["stage"] == "APPROVAL"


def test_stop_and_stage_mismatch(db, db_url, run):
    """Scenario: 자리와 단계가 다름 — 409, 아무것도 바꾸지 않는다."""
    submit(db, run)
    # 흐름은 승인 대기 자리인데 단계 칸만 손으로 반려됨으로 바꿈
    db.execute("UPDATE review_run SET stage = 'REJECTED' WHERE run_id = %s", (run,))
    db.commit()
    with pytest.raises(ReviewError) as err:
        review.reopen(db, run, user(db, "ENGINEER"))
    assert err.value.status == 409 and "흐름" in str(err.value)
    assert stage(db, run) == "REJECTED" and stop(db_url, run) == "approval"


def test_add_document_restarts_flow(db, db_url, run, tmp_path):
    """Scenario: 문서 추가 뒤 다시 멈춤 — 문서 처리부터 다시, 확정 판정 이어받기."""
    first = db.execute("SELECT min(judgment_id) FROM judgment WHERE run_id = %s AND is_current",
                       (run,)).fetchone()[0]
    review.act(ctx(db), run, "judgment", first, "CONFIRM", actor_id=user(db, "ENGINEER"))
    extra = build_gis_spec(tmp_path / "addendum_gis.docx")
    paths, merged = doc_add.prepare_add(db, run, [extra], {extra.name: {"bundle": "A"}},
                                        user(db, "ENGINEER"))
    assert execute_run(ctx(db), run, paths, merged) == "ENGINEER_REVIEW"
    assert stop(db_url, run) == "engineer_review"
    assert len(queries.run_documents(db, run)) == 2
    assert db.execute("SELECT count(*) FROM judgment WHERE run_id = %s AND is_current "
                      "AND review_status = 'CONFIRMED'", (run,)).fetchone()[0] >= 1
    assert stage(db, run) == "ENGINEER_REVIEW"


def counted(monkeypatch, name):
    real = getattr(run_mod, name)
    calls = []

    def wrapper(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)
    monkeypatch.setattr(run_mod, name, wrapper)
    return calls


def fail_judge_once(db, spec, monkeypatch):
    real = run_mod.judge_run
    state = {"failed": False}

    def judge(*args, **kwargs):
        if not state["failed"]:
            state["failed"] = True
            raise RuntimeError("판정 단계에서 멈춤")
        return real(*args, **kwargs)
    monkeypatch.setattr(run_mod, "judge_run", judge)
    run_id = create_run(db, VERSION, None)
    assert execute_run(ctx(db), run_id, [spec]) == "FAILED"
    assert queries.run_summary(db, run_id)["failed_step"] == "judge"
    return run_id


def test_retry_resumes_from_failed_step(db, db_url, spec, monkeypatch):
    """Scenario: 멈춘 단계부터 이어서 — 문서·짝·위험 조건은 다시 돌지 않는다."""
    run_id = fail_judge_once(db, spec, monkeypatch)
    docs = counted(monkeypatch, "process_document")
    risks = counted(monkeypatch, "clause_candidates")
    paths, choices = run_control.prepare_retry(db, run_id, user(db, "ENGINEER"))
    assert execute_run(ctx(db), run_id, paths, choices) == "ENGINEER_REVIEW"
    assert docs == [] and risks == []
    s = queries.run_summary(db, run_id)
    assert s["judgments"] > 0 and s["retries"] == 1
    assert stop(db_url, run_id) == "engineer_review"
    [row] = [r for r in run_log(db) if r["run_id"] == run_id]
    assert row["resumed_from"] == "judge"


def test_resumed_result_matches_full_run(db, spec, monkeypatch):
    """Scenario: 이어서 해도 결과가 같음 — 판정·위험 조건·일탈 후보 수가 같다."""
    full = create_run(db, VERSION, None)
    assert execute_run(ctx(db), full, [spec]) == "ENGINEER_REVIEW"
    resumed = fail_judge_once(db, spec, monkeypatch)
    paths, choices = run_control.prepare_retry(db, resumed, user(db, "ENGINEER"))
    assert execute_run(ctx(db), resumed, paths, choices) == "ENGINEER_REVIEW"

    def counts(run_id):
        s = queries.run_summary(db, run_id)
        dev = db.execute("SELECT count(*) FROM output_item WHERE run_id = %s "
                         "AND list_kind = 'DEVIATION'", (run_id,)).fetchone()[0]
        return s["judgments"], s["risks"], dev
    assert counts(full) == counts(resumed)


def test_run_log_empty_when_not_resumed(db, run):
    """Scenario: 처음부터 돈 검토 — 이어서 시작한 단계가 비어 있다."""
    [row] = [r for r in run_log(db) if r["run_id"] == run]
    assert row["resumed_from"] is None
