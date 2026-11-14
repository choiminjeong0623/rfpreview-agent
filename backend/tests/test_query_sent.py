"""질의 보냄 표시 (change add-query-sent, 결정 Q4).

명세 review-approval "질의 보냄 표시"의 Scenario. 질의 후보 판정에 엔지니어가 고객에게 질의를
보냈다고 표시하고 되돌린다. 판정 결과·보증값·목록은 바뀌지 않는다.
"""

import pytest

from rfp_agent.pipeline import doc_add, queries, review
from rfp_agent.pipeline.review import ReviewError
from rfp_agent.pipeline.run import RunContext, create_run, execute_run
from tests.docx_factory import build_gis_spec

VERSION = "test-dict-v1"


def ctx(conn):
    return RunContext(conn, VERSION, None, None)


def user(conn, role):
    return conn.execute("SELECT min(user_id) FROM app_user WHERE role = %s", (role,)).fetchone()[0]


def query_run(conn, spec):
    """분석을 마치고 판정 하나를 질의 후보로 고친 검토."""
    run_id = create_run(conn, VERSION, None)
    assert execute_run(ctx(conn), run_id, [spec]) == "ENGINEER_REVIEW"
    jid = conn.execute("SELECT min(judgment_id) FROM judgment WHERE run_id = %s AND is_current",
                       (run_id,)).fetchone()[0]
    review.act(ctx(conn), run_id, "judgment", jid, "EDIT", {"result": "QUERY_CANDIDATE"},
               "고객 확인 필요", user(conn, "ENGINEER"))
    return run_id, jid


def row(conn, run_id, jid):
    [j] = [r for r in queries.run_judgments(conn, run_id, limit=500) if r["judgment_id"] == jid]
    return j


def test_mark_and_undo(db, spec):
    """Scenario: 질의 보냄과 되돌리기 ·
    Scenario: 질의 보냄 표시 — 시각·표시한 사람이 남고, 되돌리면 비며, 이력에 둘 다 남는다."""
    run_id, jid = query_run(db, spec)
    eng = user(db, "ENGINEER")
    outputs = db.execute("SELECT count(*) FROM output_item WHERE run_id = %s", (run_id,)).fetchone()
    review.act(ctx(db), run_id, "judgment", jid, "QUERY_SENT", actor_id=eng)
    j = row(db, run_id, jid)
    assert j["query_sent_at"] is not None and j["query_sent_by_name"]
    assert j["result"] == "QUERY_CANDIDATE" and j["review_status"] == "EDITED"
    assert db.execute("SELECT count(*) FROM output_item WHERE run_id = %s",
                      (run_id,)).fetchone() == outputs
    with pytest.raises(ReviewError) as e:
        review.act(ctx(db), run_id, "judgment", jid, "QUERY_SENT", actor_id=eng)
    assert e.value.status == 409
    review.act(ctx(db), run_id, "judgment", jid, "QUERY_UNSENT", actor_id=eng)
    j = row(db, run_id, jid)
    assert j["query_sent_at"] is None and j["query_sent_by_name"] is None
    actions = [a for (a,) in db.execute(
        "SELECT action FROM review_log WHERE run_id = %s AND target_table = 'judgment' "
        "AND target_id = %s ORDER BY log_id", (run_id, jid))]
    assert actions[-2:] == ["QUERY_SENT", "QUERY_UNSENT"]


def test_only_query_candidate_and_engineer(db, spec):
    """Scenario: 질의 후보·엔지니어만 ·
    Scenario: 질의 후보가 아닌 판정·엔지니어가 아닌 사람은 표시할 수 없다."""
    run_id, jid = query_run(db, spec)
    other = db.execute("SELECT min(judgment_id) FROM judgment WHERE run_id = %s AND is_current "
                       "AND result <> 'QUERY_CANDIDATE'", (run_id,)).fetchone()[0]
    with pytest.raises(ReviewError) as e:
        review.act(ctx(db), run_id, "judgment", other, "QUERY_SENT",
                   actor_id=user(db, "ENGINEER"))
    assert e.value.status == 409
    with pytest.raises(ReviewError) as e:
        review.act(ctx(db), run_id, "judgment", jid, "QUERY_SENT",
                   actor_id=user(db, "APPROVER"))
    assert e.value.status == 403


def test_carry_after_addendum(db, spec, tmp_path):
    """Scenario: 문서 추가 뒤에도 남음 ·
    Scenario: 문서를 더해 다시 분석해도 같은 줄의 질의 보냄 표시가 남는다."""
    run_id, jid = query_run(db, spec)
    eng = user(db, "ENGINEER")
    review.act(ctx(db), run_id, "judgment", jid, "QUERY_SENT", actor_id=eng)
    sent = row(db, run_id, jid)["query_sent_at"]
    extra = build_gis_spec(tmp_path / "addendum_gis.docx")
    paths, merged = doc_add.prepare_add(db, run_id, [extra], {extra.name: {"bundle": "A"}}, eng)
    assert execute_run(ctx(db), run_id, paths, merged) == "ENGINEER_REVIEW"
    key = db.execute("SELECT requirement_id, value_id, product_code, compare_rule_id "
                     "FROM judgment WHERE judgment_id = %s", (jid,)).fetchone()
    new = db.execute(
        "SELECT judgment_id FROM judgment WHERE run_id = %s AND is_current AND requirement_id = %s "
        "AND value_id IS NOT DISTINCT FROM %s AND product_code IS NOT DISTINCT FROM %s "
        "AND compare_rule_id IS NOT DISTINCT FROM %s", (run_id, *key)).fetchone()[0]
    assert new != jid and row(db, run_id, new)["query_sent_at"] == sent
