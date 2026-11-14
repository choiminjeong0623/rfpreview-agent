"""판정 한꺼번에 확정. 명세 review-approval의 Scenario (add-bulk-confirm)."""

import pytest

from rfp_agent.pipeline import queries, review
from rfp_agent.pipeline.run import RunContext, create_run, execute_run, switch_product

VERSION = "test-dict-v1"


def run_once(conn, paths):
    run_id = create_run(conn, VERSION, None)
    assert execute_run(RunContext(conn, VERSION, None, None), run_id, paths) == "ENGINEER_REVIEW"
    return run_id


def ctx(conn):
    return RunContext(conn, VERSION, None, None)


def logs(conn, run_id):
    return conn.execute("SELECT count(*) FROM review_log WHERE run_id = %s AND target_table = "
                        "'judgment' AND action = 'CONFIRM'", (run_id,)).fetchone()[0]


def test_bulk_confirm_comply(db, spec):
    """Scenario: 준수 모두 확정 — 3줄 확정, 결과 그대로, 이력 3건."""
    run_id = run_once(db, [spec])
    comply = [j for j in queries.run_judgments(db, run_id, limit=500)
              if j["result"] == "COMPLY" and j["review_status"] == "CANDIDATE"][:3]
    assert len(comply) == 3
    ids = [j["judgment_id"] for j in comply]
    out = review.bulk_confirm(ctx(db), run_id, ids)
    assert out["confirmed"] == 3
    after = {j["judgment_id"]: j for j in queries.run_judgments(db, run_id, limit=500)}
    assert [(after[i]["result"], after[i]["review_status"]) for i in ids] == [
        ("COMPLY", "CONFIRMED")] * 3
    assert logs(db, run_id) == 3


def test_bulk_confirm_stale_row(db, spec):
    """Scenario: 현재 판정이 아닌 줄이 섞임 — 오류, 아무 줄도 확정되지 않고 이력 없음."""
    run_id = run_once(db, [spec])
    rows = queries.run_judgments(db, run_id, limit=500)
    gis = next(j for j in rows if j["product_code"] == "GIS-145")
    other = next(j for j in rows if j["equipment_group"] != gis["equipment_group"])
    switch_product(ctx(db), run_id, gis["equipment_group"], "GIS-145-P7")
    with pytest.raises(review.ReviewError) as err:
        review.bulk_confirm(ctx(db), run_id, [other["judgment_id"], gis["judgment_id"]])
    assert err.value.status == 409
    status = db.execute("SELECT review_status FROM judgment WHERE judgment_id = %s",
                        (other["judgment_id"],)).fetchone()[0]
    assert status == "CANDIDATE" and logs(db, run_id) == 0


def test_bulk_confirm_while_waiting_approval(db, spec):
    """Scenario: 승인 대기 중 한꺼번에 확정 — 담당자 확인 단계 오류, 바뀌지 않음."""
    run_id = run_once(db, [spec])
    j = queries.run_judgments(db, run_id, limit=1)[0]
    review.finish_review(db, run_id, review.default_user(db, "APPROVER"), "확인")
    with pytest.raises(review.ReviewError) as err:
        review.bulk_confirm(ctx(db), run_id, [j["judgment_id"]])
    assert "담당자 확인" in str(err.value)
    assert logs(db, run_id) == 0


def test_bulk_confirm_api(db, db_url, spec, monkeypatch):
    """한꺼번에 확정 API: 판정 확정만 받고, 빈 목록은 400."""
    from fastapi.testclient import TestClient

    from rfp_agent.api.main import app
    from rfp_agent.config import get_settings

    run_id = run_once(db, [spec])
    ids = [j["judgment_id"] for j in queries.run_judgments(db, run_id, limit=2)]
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    get_settings.cache_clear()
    try:
        client = TestClient(app)
        url = f"/api/runs/{run_id}/actions/bulk"
        assert client.post(url, json={"target": "risk_flag", "ids": ids}).status_code == 400
        assert client.post(url, json={"ids": ids, "action": "REJECT"}).status_code == 400
        assert client.post(url, json={"ids": []}).status_code == 400
        res = client.post(url, json={"ids": ids})
        assert res.status_code == 200 and res.json()["confirmed"] == 2
    finally:
        get_settings.cache_clear()


# ── 한꺼번에 확정 가드 (update-bulk-confirm-guard) ─────────────────────

def candidates(conn, run_id, result="COMPLY"):
    rows = conn.execute("SELECT judgment_id, value_id FROM judgment WHERE run_id = %s "
                        "AND result = %s AND review_status = 'CANDIDATE' AND is_current "
                        "AND value_id IS NOT NULL ORDER BY judgment_id", (run_id, result))
    return [{"judgment_id": i, "value_id": v} for i, v in rows]


def status_of(conn, judgment_id):
    return conn.execute("SELECT review_status FROM judgment WHERE judgment_id = %s",
                        (judgment_id,)).fetchone()[0]


def test_bulk_confirm_skips_check_violation(db, spec):
    """Scenario: 검산 위반 줄은 뺌 — 준수 2줄만 확정, 위반 줄은 후보 그대로."""
    run_id = run_once(db, [spec])
    bad, *ok = candidates(db, run_id)[:3]
    v = bad["value_id"]
    db.execute("INSERT INTO engineering_check (run_id, ik_value_id, peak_value_id, freq_value_id, "
               "expected_ka, factor, result) VALUES (%s, %s, %s, %s, 125, 2.5, 'VIOLATION')",
               (run_id, v, v, v))
    ids = [bad["judgment_id"]] + [j["judgment_id"] for j in ok]
    out = review.bulk_confirm(ctx(db), run_id, ids)
    assert out["confirmed"] == 2
    assert out["skipped"] == [{"judgment_id": bad["judgment_id"], "reason": "CHECK"}]
    assert status_of(db, bad["judgment_id"]) == "CANDIDATE"
    assert all(status_of(db, j["judgment_id"]) == "CONFIRMED" for j in ok)
    assert logs(db, run_id) == 2


def test_bulk_confirm_skips_number_mismatch(db, spec):
    """Scenario: 숫자 불일치 줄은 뺌 — 연결된 목록 문장이 불일치인 판정은 빠진다."""
    run_id = run_once(db, [spec])
    item_id, judgment_id = db.execute(
        """SELECT s.item_id, s.judgment_id FROM output_item_source s JOIN output_item o
           USING (item_id) WHERE o.run_id = %s AND s.judgment_id IS NOT NULL LIMIT 1""",
        (run_id,)).fetchone()
    db.execute("UPDATE output_item SET number_check = 'MISMATCH' WHERE item_id = %s", (item_id,))
    other = next(j["judgment_id"] for j in candidates(db, run_id)
                 if j["judgment_id"] != judgment_id)
    out = review.bulk_confirm(ctx(db), run_id, [judgment_id, other])
    assert out["confirmed"] == 1
    assert out["skipped"] == [{"judgment_id": judgment_id, "reason": "MISMATCH"}]
    assert status_of(db, other) == "CONFIRMED"


def test_bulk_confirm_skips_empty_value(db, spec):
    """Scenario: 값이 빈 줄은 뺌 — 모두 빠지면 오류, 아무것도 바뀌지 않음."""
    run_id = run_once(db, [spec])
    j = candidates(db, run_id)[0]
    db.execute("UPDATE judgment SET result = 'NEEDS_REVIEW', product_value_raw = NULL, "
               "margin_direction = 'NOT_CALC' WHERE judgment_id = %s", (j["judgment_id"],))
    with pytest.raises(review.ReviewError) as err:
        review.bulk_confirm(ctx(db), run_id, [j["judgment_id"]])
    assert err.value.status == 400 and "한 줄씩" in str(err.value)
    assert status_of(db, j["judgment_id"]) == "CANDIDATE" and logs(db, run_id) == 0
    other = candidates(db, run_id)[0]["judgment_id"]
    out = review.bulk_confirm(ctx(db), run_id, [j["judgment_id"], other])
    assert out["confirmed"] == 1 and out["skipped"][0]["reason"] == "NO_VALUE"
