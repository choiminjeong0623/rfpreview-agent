"""AR-03 직접 작성할 칸 (change update-review-ratio-hand-fill, 명세 review-approval)."""

import pytest

from rfp_agent.pipeline import review
from rfp_agent.pipeline.run import RunContext, create_run, execute_run

VERSION = "test-dict-v1"


@pytest.fixture
def run(db, spec):
    run_id = create_run(db, VERSION, None)
    assert execute_run(RunContext(db, VERSION, None, None), run_id, [spec]) == "ENGINEER_REVIEW"
    return run_id


def warranty_ids(db, run_id):
    return [r[0] for r in db.execute(
        """SELECT w.judgment_id FROM warranty_candidate w JOIN judgment j USING (judgment_id)
           WHERE j.run_id = %s AND j.is_current ORDER BY 1""", (run_id,))]


def set_reason(db, judgment_ids, reason):
    db.execute("UPDATE warranty_candidate SET status = 'EMPTY_REVIEW', reason_code = %s, "
               "candidate_value = NULL WHERE judgment_id = ANY(%s)", (reason, judgment_ids))


def test_hand_fill_left_out_of_ratio(db, run):
    """Scenario: 직접 작성할 칸은 비율에서 뺌.

    보증값 칸이 모두 제품표에 연결되지 않은 빈칸이면 확인 필요 수·전체 수에서 빠지고
    직접 작성할 칸 수가 그 칸 수와 같으며, 그 칸 때문에 AR-03이 걸리지 않는다.
    """
    ids = warranty_ids(db, run)
    assert len(ids) >= 2
    judged = db.execute("SELECT count(*) FROM judgment WHERE run_id = %s AND is_current "
                        "AND review_status <> 'REJECTED'", (run,)).fetchone()[0]
    set_reason(db, ids, "NOT_MAPPED")
    ratio = review.review_ratio(db, run)
    assert ratio["hand_fill"] == len(ids)
    assert ratio["total"] == judged - len(ids)
    needs = db.execute("SELECT count(*) FROM judgment WHERE run_id = %s AND is_current "
                       "AND review_status = 'CANDIDATE' AND result = 'NEEDS_REVIEW' "
                       "AND judgment_id <> ALL(%s)", (run, ids)).fetchone()[0]
    assert ratio["review"] == needs
    # AR-03은 빈칸을 뺀 비율로만 판단한다
    ar03 = [c for c in review.criteria(db, run) if c.ar_code == "AR-03"]
    assert bool(ar03) == (ratio["total"] > 0 and needs / ratio["total"] > ratio["threshold"])
    # 확인 필요 줄을 모두 확정하면 빈칸이 아무리 많아도 AR-03은 걸리지 않는다
    db.execute("UPDATE judgment SET review_status = 'CONFIRMED' WHERE run_id = %s "
               "AND result = 'NEEDS_REVIEW' AND judgment_id <> ALL(%s)", (run, ids))
    assert review.review_ratio(db, run)["review"] == 0
    assert not [c for c in review.criteria(db, run) if c.ar_code == "AR-03"]
    # 예전 계산이면 빈칸이 모두 확인 필요로 들어가 비율이 훨씬 높았다
    assert (needs + len(ids)) / judged > needs / max(ratio["total"], 1)


def test_suspicious_empty_still_counts(db, run):
    """Scenario: 의심할 빈칸은 그대로 셈 — 제품을 고르지 못한 빈칸은 확인 필요에 든다."""
    ids = warranty_ids(db, run)
    set_reason(db, ids, "NOT_MAPPED")
    before = review.review_ratio(db, run)
    set_reason(db, ids[:1], "PRODUCT_AMBIGUOUS")
    after = review.review_ratio(db, run)
    assert after["hand_fill"] == before["hand_fill"] - 1
    assert after["review"] == before["review"] + 1
    assert after["total"] == before["total"] + 1


def test_approval_screen_has_hand_fill(db, run):
    """승인 화면 응답의 확인 필요 비율에 직접 작성할 칸 수가 있다."""
    ids = warranty_ids(db, run)
    set_reason(db, ids, "NOT_MAPPED")
    assert review.approval(db, run)["review_ratio"]["hand_fill"] == len(ids)
