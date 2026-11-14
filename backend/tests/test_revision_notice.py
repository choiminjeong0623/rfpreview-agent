"""개정 안내 (change add-revision-notice).

명세 review-run "문서 추가 개정 결과"의 Scenario. 문서를 더해 다시 판정하면
같은 줄(요구값·비교 제품·비교 규칙) 기준으로 바뀜·추가·사라짐을 남긴다.
"""

from rfp_agent.pipeline import doc_add, queries
from rfp_agent.pipeline.run import RunContext, create_run, execute_run
from tests.docx_factory import build_gis_spec

VERSION = "test-dict-v1"


def ctx(conn):
    return RunContext(conn, VERSION, None, None)


def engineer(conn):
    return conn.execute("SELECT min(user_id) FROM app_user WHERE role = 'ENGINEER'").fetchone()[0]


def finished(conn, spec):
    run_id = create_run(conn, VERSION, None)
    assert execute_run(ctx(conn), run_id, [spec]) == "ENGINEER_REVIEW"
    return run_id


def add(conn, run_id, extra):
    paths, merged = doc_add.prepare_add(conn, run_id, [extra], {extra.name: {"bundle": "A"}},
                                        engineer(conn))
    assert execute_run(ctx(conn), run_id, paths, merged) == "ENGINEER_REVIEW"


def test_no_revision_without_addendum(db, spec):
    """Scenario: 문서를 더하지 않은 검토 — 개정 없음, 판정 줄에 개정 표시 없음."""
    run_id = finished(db, spec)
    assert queries.run_summary(db, run_id)["revision"] is None
    rows = queries.run_judgments(db, run_id, limit=5)
    assert rows and all(r["revised"] is None for r in rows)
    assert queries.count_judgments(db, run_id, revised=True) == 0


def test_revision_counts(db, spec, tmp_path):
    """Scenario: 개정 결과 줄 수 — 개정 1, 더한 파일 이름, 추가 줄 수, 목록 응답에도."""
    run_id = finished(db, spec)
    before = queries.count_judgments(db, run_id)
    add(db, run_id, build_gis_spec(tmp_path / "addendum_gis.docx"))
    rev = queries.run_summary(db, run_id)["revision"]
    after = queries.count_judgments(db, run_id)
    assert rev["no"] == 1 and rev["files"] == ["addendum_gis.docx"] and rev["at"]
    assert rev["added"] == after - before + rev["removed"] and rev["added"] > 0
    assert rev["changed"] == 0
    [listed] = [r for r in queries.run_list(db, 200) if r["run_id"] == run_id]
    assert listed["revision"]["added"] == rev["added"]
    # 표시는 한 번만 남는다: 같은 판정 단계를 다시 돌려도 개정 번호가 늘지 않는다
    state = db.execute("SELECT graph_state ? 'revision_pending' FROM review_run "
                       "WHERE run_id = %s", (run_id,)).fetchone()[0]
    assert state is False


def test_changed_rows_filter(db, spec, tmp_path):
    """Scenario: 바뀐 줄만 보기 — 판정 값이 달라진 같은 줄은 "바뀜", 거르면 바뀜·추가 줄만."""
    run_id = finished(db, spec)
    # 처음 분석에서 한 줄의 판정이 달랐던 것으로 만든다 (사람이 손대지 않은 후보 줄)
    jid, result = db.execute(
        "SELECT judgment_id, result FROM judgment WHERE run_id = %s AND is_current "
        "AND review_status = 'CANDIDATE' ORDER BY judgment_id LIMIT 1", (run_id,)).fetchone()
    other = "QUERY_CANDIDATE" if result != "QUERY_CANDIDATE" else "COMPLY"
    db.execute("UPDATE judgment SET result = %s, margin_direction = 'NOT_CALC' "
               "WHERE judgment_id = %s", (other, jid))
    db.commit()
    add(db, run_id, build_gis_spec(tmp_path / "addendum_gis.docx"))
    rev = queries.run_summary(db, run_id)["revision"]
    assert rev["changed"] == 1
    rows = queries.run_judgments(db, run_id, revised=True, limit=500)
    assert len(rows) == queries.count_judgments(db, run_id, revised=True)
    kinds = [r["revised"] for r in rows]
    assert kinds.count("CHANGED") == 1 and set(kinds) <= {"CHANGED", "ADDED"}
    [changed] = [r for r in rows if r["revised"] == "CHANGED"]
    assert changed["result"] == result and changed["judgment_id"] != jid
