"""지난 사람 판정 힌트 (change add-review-memory, 명세 review-approval)."""

import pytest

from rfp_agent.pipeline import queries, review
from rfp_agent.pipeline.run import RunContext, create_run, execute_run
from tests.conftest import FakeLLM

VERSION = "test-dict-v1"


def new_run(db, spec):
    run_id = create_run(db, VERSION, None)
    assert execute_run(RunContext(db, VERSION, None, None), run_id, [spec]) == "ENGINEER_REVIEW"
    return run_id


def act(db, run_id, judgment_id, action, value=None, reason=None):
    review.act(RunContext(db, VERSION, FakeLLM(), None), run_id, "judgment", judgment_id,
               action, value, reason)


def comply(db, run_id, n=1):
    ids = [r[0] for r in db.execute(
        "SELECT judgment_id FROM judgment WHERE run_id = %s AND is_current AND result = 'COMPLY' "
        "ORDER BY judgment_id LIMIT %s", (run_id, n))]
    assert len(ids) == n
    return ids


def same_line(db, old_id, new_run_id):
    """앞 검토 판정과 같은 요구 줄의 새 검토 판정 (같은 문서는 처리 결과를 다시 쓴다)."""
    return db.execute(
        """SELECT n.judgment_id FROM judgment o JOIN judgment n
              ON n.requirement_id = o.requirement_id AND n.value_id = o.value_id
           WHERE o.judgment_id = %s AND n.run_id = %s AND n.is_current""",
        (old_id, new_run_id)).fetchone()[0]


def listed(db, run_id, **kw):
    return {j["judgment_id"]: j for j in queries.run_judgments(db, run_id, limit=500, **kw)}


@pytest.fixture
def first(db, spec):
    return new_run(db, spec)


def test_edited_in_past_run(db, spec, first):
    """Scenario: 지난 검토에서 고친 판정 — 새 검토 같은 줄에 지난 확정, 다름, 판정 값은 그대로."""
    [old] = comply(db, first)
    act(db, first, old, "EDIT", {"result": "DEVIATION_CANDIDATE"}, "보증 조건이 다름")
    second = new_run(db, spec)
    new = same_line(db, old, second)
    row = listed(db, second)[new]
    past = row["past_decision"]
    assert past["result"] == "DEVIATION_CANDIDATE" and past["same"] is False
    assert past["run_id"] == first and past["review_no"].endswith(f"{first:03d}")
    assert past["reason"] == "보증 조건이 다름" and past["review_status"] == "EDITED"
    assert row["result"] == "COMPLY" and row["review_status"] == "CANDIDATE"
    # 칩 건수와 거르기
    counts = queries.judgment_counts(db, second)
    assert counts["past_differs"] == 1 and counts["past_seen"] >= 1
    assert list(listed(db, second, past="differs")) == [new]
    assert queries.count_judgments(db, second, past="differs") == 1


def test_confirmed_in_past_run(db, spec, first):
    """Scenario: 지난 검토에서 그대로 확정 — 지난 확정이 있고 같음."""
    [old] = comply(db, first)
    act(db, first, old, "CONFIRM")
    second = new_run(db, spec)
    past = listed(db, second)[same_line(db, old, second)]["past_decision"]
    assert past["result"] == "COMPLY" and past["same"] is True
    assert queries.judgment_counts(db, second)["past_differs"] == 0


def test_unreviewed_or_rejected(db, spec, first):
    """Scenario: 사람이 보지 않은 줄 — 확정하지 않았거나 반려한 줄은 지난 확정이 없다."""
    a, b = comply(db, first, 2)
    act(db, first, b, "REJECT", reason="해당 없음")
    second = new_run(db, spec)
    rows = listed(db, second)
    assert rows[same_line(db, a, second)]["past_decision"] is None
    assert rows[same_line(db, b, second)]["past_decision"] is None
    assert queries.judgment_counts(db, second)["past_seen"] == 0


def test_other_product_no_hint(db, spec, first):
    """Scenario: 제품이 다르면 힌트 없음."""
    [old] = comply(db, first)
    act(db, first, old, "CONFIRM")
    second = new_run(db, spec)
    new = same_line(db, old, second)
    other = db.execute("SELECT product_code FROM product_master WHERE product_code <> "
                       "(SELECT product_code FROM judgment WHERE judgment_id = %s) LIMIT 1",
                       (new,)).fetchone()[0]
    db.execute("UPDATE judgment SET product_code = %s WHERE judgment_id = %s", (other, new))
    assert listed(db, second)[new]["past_decision"] is None


def test_same_hint_twice(db, spec, first):
    """같은 입력이면 같은 힌트 (CR-11)."""
    [old] = comply(db, first)
    act(db, first, old, "EDIT", {"result": "QUERY_CANDIDATE"}, "확인")
    second = new_run(db, spec)
    assert listed(db, second) == listed(db, second)
