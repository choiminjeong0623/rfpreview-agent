"""지난 RFP 비교 (add-past-compare). 명세 review-run "지난 검토 비교"의 Scenario."""

import pytest

from rfp_agent.pipeline import past_compare
from rfp_agent.pipeline.run import RunContext, create_run, execute_run
from tests.docx_factory import build_judgment_spec, build_judgment_spec_next

VERSION = "test-dict-v1"


def finished(conn, path, customer, bundle="A"):
    run_id = create_run(conn, VERSION, None)
    conn.execute("UPDATE review_run SET customer_name = %s WHERE run_id = %s", (customer, run_id))
    conn.commit()
    assert execute_run(RunContext(conn, VERSION, None, None), run_id, [path],
                       {path.name: {"bundle": bundle}}) == "ENGINEER_REVIEW"
    return run_id


@pytest.fixture
def pair(db, tmp_path):
    past = finished(db, build_judgment_spec(tmp_path / "synthetic_judgment.docx"), "예시 송전회사")
    now = finished(db, build_judgment_spec_next(tmp_path / "next_datasheet.docx"),
                   " 예시  송전회사 ")
    return past, now


def test_targets_same_customer(db, pair, tmp_path):
    """Scenario: 같은 고객의 지난 검토 — 고객사 글자가 같은(공백·대소문자 무시) 다른 검토만 온다."""
    past, now = pair
    finished(db, build_judgment_spec(tmp_path / "other.docx"), "다른 고객사")
    got = past_compare.targets(db, now)
    assert got["customer_name"] == "예시  송전회사"
    assert [t["run_id"] for t in got["targets"]] == [past]
    t = got["targets"][0]
    assert t["review_no"].startswith("RV-") and t["judgments"] > 0 and t["products"]


def test_targets_without_customer(db, tmp_path):
    """Scenario: 고객사가 비어 있음 — 대상이 없고 고객사도 비어 온다."""
    run_id = finished(db, build_judgment_spec(tmp_path / "synthetic_judgment.docx"), "")
    assert past_compare.targets(db, run_id) == {"customer_name": None, "targets": []}


def test_compare_kinds(db, pair):
    """Scenario: 달라진 요구만 — 값 바뀜·새로 생김·사라짐 한 줄씩, 같은 요구는 숨긴 수로."""
    past, now = pair
    got = past_compare.compare(db, now, past)
    by = {(r["kind"], r["before"], r["after"]): r for r in got["rows"]}
    chg = by[("chg", "4000 A", "3150 A")]
    assert chg["equipment"] == "245 kV GIS" and "요구 값이 내려감" in chg["note"]
    assert chg["requirement_id"]
    new = by[("new", "—", "125 kA")]
    assert new["before_result"] is None and new["after_result"]
    assert new["note"] == "지난번에 없던 요구"
    gone = by[("del", "3500 A", "—")]
    assert gone["after_result"] is None and gone["requirement_id"] is None
    assert gone["note"].startswith("이번에는 요구 없음")
    assert [r["kind"] for r in got["rows"]] == sorted(
        (r["kind"] for r in got["rows"]), key=past_compare.KIND_ORDER.get)
    assert len(got["rows"]) == 3 and got["same"] > 5
    assert got["target"]["run_id"] == past


def test_compare_result_change_same_value(db, pair):
    """Scenario: 값은 같고 판정만 바뀜 — 사람이 수정한 판정 값으로 비교한다."""
    past, now = pair
    jid = db.execute(
        """SELECT j.judgment_id FROM judgment j JOIN req_value v USING (value_id)
           WHERE j.run_id = %s AND j.is_current AND v.item_key = 'rated_frequency'
           ORDER BY 1 LIMIT 1""", (past,)).fetchone()[0]
    db.execute("UPDATE judgment SET result = 'QUERY_CANDIDATE', review_status = 'EDITED' "
               "WHERE judgment_id = %s", (jid,))
    db.commit()
    got = past_compare.compare(db, now, past)
    [row] = [r for r in got["rows"] if r["before_result"] == "QUERY_CANDIDATE"]
    assert row["kind"] == "chg" and row["before"] == row["after"]
    assert row["note"] == "요구 값 같음 · 판정 바뀜"


def test_compare_is_reproducible(db, pair):
    """같은 두 검토면 같은 결과 (CR-11)."""
    past, now = pair
    assert past_compare.compare(db, now, past) == past_compare.compare(db, now, past)


def test_compare_rejects(db, pair):
    """같은 검토끼리, 없는 검토는 거절."""
    past, now = pair
    with pytest.raises(ValueError):
        past_compare.compare(db, now, now)
    with pytest.raises(past_compare.NotFound):
        past_compare.compare(db, now, 999999)


def test_compare_api(db, db_url, monkeypatch, pair):
    """비교 API: 대상 목록과 비교 결과, 같은 검토 400, 없는 검토 404."""
    from fastapi.testclient import TestClient

    from rfp_agent.api.main import app
    from rfp_agent.config import get_settings

    past, now = pair
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    get_settings.cache_clear()
    try:
        client = TestClient(app)
        res = client.get(f"/api/runs/{now}/compare")
        assert res.status_code == 200 and res.json()["targets"][0]["run_id"] == past
        res = client.get(f"/api/runs/{now}/compare/{past}")
        assert res.status_code == 200 and len(res.json()["rows"]) == 3
        assert client.get(f"/api/runs/{now}/compare/{now}").status_code == 400
        assert client.get(f"/api/runs/{now}/compare/999999").status_code == 404
    finally:
        get_settings.cache_clear()


def test_compare_skips_rejected(db, pair):
    """Scenario: 반려한 판정은 뺌 — 이번에 반려한 줄은 빠져 지난 쪽만 남아 사라짐으로 보인다."""
    past, now = pair
    jid = db.execute(
        """SELECT j.judgment_id FROM judgment j JOIN req_value v USING (value_id)
           WHERE j.run_id = %s AND j.is_current AND v.item_key = 'rated_voltage_um'
           ORDER BY 1 LIMIT 1""", (now,)).fetchone()[0]
    db.execute("UPDATE judgment SET review_status = 'REJECTED' WHERE judgment_id = %s", (jid,))
    db.commit()
    rows = past_compare.compare(db, now, past)["rows"]
    gone = [r for r in rows if r["kind"] == "del" and r["before"] == "245 kV"]
    assert len(gone) == 1 and gone[0]["equipment"] == "245 kV GIS"
