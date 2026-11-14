"""검토 취소와 다시 시도.

명세 review-run "검토 취소"·"검토 다시 시도"의 Scenario (change add-run-control).
"""

import psycopg
import pytest

from rfp_agent.pipeline import queries, run_control
from rfp_agent.pipeline.review import ReviewError
from rfp_agent.pipeline.run import RunContext, create_run, execute_run
from tests.docx_factory import build_judgment_spec

VERSION = "test-dict-v1"


def count(conn, table):
    return conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def engineer(conn):
    return conn.execute("SELECT min(user_id) FROM app_user WHERE role = 'ENGINEER'").fetchone()[0]


def cancel_on_first_report(db_url, actor):
    """처음 세부 진행을 기록할 때 다른 연결로 취소를 요청한다 (화면에서 누른 것처럼)."""
    def progress(run_id, detail):
        if progress.done:
            return
        progress.done = True
        with psycopg.connect(db_url, autocommit=True) as other:
            run_control.request_cancel(other, run_id, actor)
    progress.done = False
    return progress


def test_cancel_while_processing(db, db_url, spec):
    """Scenario: 처리 중 취소 — 다음 진행 기록에서 멈추고 그 문서는 저장되지 않는다."""
    actor = engineer(db)
    run_id = create_run(db, VERSION, None)
    ctx = RunContext(db, VERSION, None, None, cancel_on_first_report(db_url, actor))
    assert execute_run(ctx, run_id, [spec]) == "FAILED"
    s = queries.run_summary(db, run_id)
    assert (s["stage"], s["failed_step"]) == ("FAILED", "documents")
    assert s["error_message"].endswith("분석을 취소했습니다.")
    assert s["cancel_requested_at"] is not None and s["retryable"] is True
    assert count(db, "document") == 0 and s["documents"] == 0


def test_cancel_stalled_run(db, spec):
    """Scenario: 멈춘 검토 취소 — 마지막 진행이 11분 전이면 바로 처리 실패."""
    run_id = create_run(db, VERSION, None)
    db.execute("""UPDATE review_run SET graph_state = graph_state || jsonb_build_object(
                    'step', 'documents', 'updated_at', now() - interval '11 minutes')
                  WHERE run_id = %s""", (run_id,))
    db.commit()
    run_control.request_cancel(db, run_id, engineer(db))
    s = queries.run_summary(db, run_id)
    assert (s["stage"], s["failed_step"]) == ("FAILED", "documents")
    assert "진행이 10분 넘게 멈춰" in s["error_message"]


def test_cannot_cancel_finished_run(db, spec):
    """Scenario: 끝난 검토는 취소 못 함 — 409, 검토는 그대로."""
    run_id = create_run(db, VERSION, None)
    assert execute_run(RunContext(db, VERSION, None, None), run_id, [spec]) == "ENGINEER_REVIEW"
    with pytest.raises(ReviewError) as err:
        run_control.request_cancel(db, run_id, engineer(db))
    assert err.value.status == 409
    s = queries.run_summary(db, run_id)
    assert s["stage"] == "ENGINEER_REVIEW" and s["cancel_requested_at"] is None


def test_retry_cancelled_run(db, db_url, spec):
    """Scenario: 취소한 검토 다시 시도 — 같은 검토로 담당자 확인까지, 판정이 나오고 횟수 1."""
    actor = engineer(db)
    run_id = create_run(db, VERSION, None)
    ctx = RunContext(db, VERSION, None, None, cancel_on_first_report(db_url, actor))
    assert execute_run(ctx, run_id, [spec]) == "FAILED"
    paths, choices = run_control.prepare_retry(db, run_id, actor)
    assert paths == [spec] and choices == {}
    s = queries.run_summary(db, run_id)
    assert (s["stage"], s["failed_step"], s["error_message"], s["cancel_requested_at"]) == \
        ("PROCESSING", None, None, None)
    assert execute_run(RunContext(db, VERSION, None, None), run_id, paths, choices) \
        == "ENGINEER_REVIEW"
    s = queries.run_summary(db, run_id)
    assert s["retries"] == 1 and s["judgments"] > 0 and s["retryable"] is False


def test_retry_reuses_processed_document(db, spec, tmp_path, monkeypatch):
    """Scenario: 처리한 문서는 다시 씀 — 새 문서 줄은 두 번째 문서 하나만 생긴다."""
    from rfp_agent.pipeline import run as run_mod
    second = build_judgment_spec(tmp_path / "second_datasheet.docx")
    choices = {second.name: {"bundle": "B"}}
    real = run_mod.process_document
    calls = []

    def fail_second(conn, path, *args, **kwargs):
        calls.append(path.name)
        # 문서를 동시에 처리하면 부르는 순서가 바뀌므로 두 번째 문서의 첫 처리에서 멈춘다
        if path.name == second.name and calls.count(second.name) == 1:
            raise RuntimeError("두 번째 문서에서 멈춤")
        return real(conn, path, *args, **kwargs)

    monkeypatch.setattr(run_mod, "process_document", fail_second)
    run_id = create_run(db, VERSION, None)
    assert execute_run(RunContext(db, VERSION, None, None), run_id, [spec, second],
                       choices) == "FAILED"
    first_doc = db.execute("SELECT document_id FROM document").fetchall()
    assert len(first_doc) == 1
    paths, saved = run_control.prepare_retry(db, run_id, engineer(db))
    assert saved == choices
    assert execute_run(RunContext(db, VERSION, None, None), run_id, paths, saved) \
        == "ENGINEER_REVIEW"
    docs = queries.run_documents(db, run_id)
    assert count(db, "document") == 2
    assert first_doc[0][0] in [d["document_id"] for d in docs]


def test_retry_without_inputs(db):
    """Scenario: 다시 돌릴 파일 정보 없음 — 409와 다시 등록 안내, 검토는 그대로."""
    run_id = create_run(db, VERSION, None)
    db.execute("UPDATE review_run SET stage = 'FAILED', failed_step = 'documents' "
               "WHERE run_id = %s", (run_id,))
    db.commit()
    with pytest.raises(ReviewError) as err:
        run_control.prepare_retry(db, run_id, engineer(db))
    assert err.value.status == 409 and "다시 등록" in str(err.value)
    assert queries.run_summary(db, run_id)["stage"] == "FAILED"


def test_retry_only_failed(db, spec):
    run_id = create_run(db, VERSION, None)
    assert execute_run(RunContext(db, VERSION, None, None), run_id, [spec]) == "ENGINEER_REVIEW"
    with pytest.raises(ReviewError) as err:
        run_control.prepare_retry(db, run_id, engineer(db))
    assert err.value.status == 409
