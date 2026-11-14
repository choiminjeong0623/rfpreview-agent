"""단계부터 다시 처리 (change add-step-rewind, C2).

명세 review-approval "단계부터 다시 처리"의 Scenario. 화면은 frontend/e2e/step-rewind.spec.ts.
"""

import pytest

from rfp_agent.pipeline import doc_add, graph_flow, queries, review
from rfp_agent.pipeline.review import ReviewError
from rfp_agent.pipeline.run import RunContext, create_run, execute_run

VERSION = "test-dict-v1"
REASON = "판정 규칙을 고쳐서 다시 판정"


def ctx(conn):
    return RunContext(conn, VERSION, None, None)


def user(conn, role):
    return review.default_user(conn, role)


@pytest.fixture
def run(db, spec):
    run_id = create_run(db, VERSION, None)
    assert execute_run(ctx(db), run_id, [spec]) == "ENGINEER_REVIEW"
    return run_id


def current(conn, run_id):
    return {r[0]: r[1:] for r in conn.execute(
        """SELECT (requirement_id, value_id, product_code, compare_rule_id)::text,
                  judgment_id, review_status, result
           FROM judgment WHERE run_id = %s AND is_current""", (run_id,))}


def test_rewind_from_judge_keeps_edit(db, run):
    """Scenario: 판정부터 다시 처리 — 다시 멈추고, 수정한 줄 그대로, 이력·흐름 기록에 남음."""
    (key, (jid, _, result)) = sorted(current(db, run).items())[0]
    new_result = "QUERY_CANDIDATE" if result != "QUERY_CANDIDATE" else "COMPLY"
    review.act(ctx(db), run, "judgment", jid, "EDIT", {"result": new_result}, "고객 확인",
               user(db, "ENGINEER"))
    paths, choices = doc_add.prepare_rewind(db, run, "judge", REASON, user(db, "ENGINEER"))
    assert queries.run_summary(db, run)["stage"] == "PROCESSING"
    assert execute_run(ctx(db), run, paths, choices, "judge") == "ENGINEER_REVIEW"
    after = current(db, run)
    assert after[key][1:] == ("EDITED", new_result) and after[key][0] != jid   # 새 줄에 이어받음
    [(value, reason)] = db.execute(
        "SELECT after_value, reason FROM review_log WHERE run_id = %s AND action = 'REWIND'",
        (run,)).fetchall()
    assert (value, reason) == ({"step": "judge"}, REASON)
    flow = graph_flow.history(db, run)
    rewound = [s for s in flow["steps"] if s["action"] == "rewind"]
    assert [s["node"] for s in rewound] == ["engineer_review"]
    assert flow["stop"] == "engineer_review"
    nodes = [s["node"] for s in flow["steps"]]
    assert nodes[nodes.index("engineer_review") + 1] == "judge"           # 문서 읽기는 다시 안 함


def test_rewind_refused_after_submit(db, run):
    """Scenario: 상신한 검토는 못 되돌림 — 409, 단계·흐름 그대로."""
    review.finish_review(db, run, user(db, "APPROVER"), "상신합니다", user(db, "ENGINEER"))
    with pytest.raises(ReviewError) as err:
        doc_add.prepare_rewind(db, run, "judge", REASON, user(db, "ENGINEER"))
    assert err.value.status == 409
    assert queries.run_summary(db, run)["stage"] == "APPROVAL"
    assert graph_flow.history(db, run)["stop"] == "approval"


def test_rewind_refused_for_approver(db, run):
    """Scenario: 승인자는 못 되돌림 — 403."""
    with pytest.raises(ReviewError) as err:
        doc_add.prepare_rewind(db, run, "judge", REASON, user(db, "APPROVER"))
    assert err.value.status == 403


@pytest.mark.parametrize(("step", "reason"), [("engineer_review", REASON), ("judge", "  ")])
def test_rewind_refuses_bad_input(db, run, step, reason):
    """처리 단계가 아닌 이름·빈 사유는 400, 단계는 그대로."""
    with pytest.raises(ReviewError) as err:
        doc_add.prepare_rewind(db, run, step, reason, user(db, "ENGINEER"))
    assert err.value.status == 400
    assert queries.run_summary(db, run)["stage"] == "ENGINEER_REVIEW"


def test_rewind_refused_without_flow(db, spec):
    """흐름 기록이 없는 검토(이 기능 전 방식으로 끝남)는 409."""
    run_id = create_run(db, VERSION, None)
    db.execute("UPDATE review_run SET stage = 'ENGINEER_REVIEW', graph_state = graph_state || "
               "jsonb_build_object('inputs', jsonb_build_object('paths', "
               "jsonb_build_array(%s::text))) WHERE run_id = %s", (str(spec), run_id))
    with pytest.raises(ReviewError) as err:
        doc_add.prepare_rewind(db, run_id, "judge", REASON, user(db, "ENGINEER"))
    assert err.value.status == 409
