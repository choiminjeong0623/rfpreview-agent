"""기준 데이터 읽기 (add-reference-views). 명세 reference-data의 Scenario."""

import pytest

from rfp_agent.pipeline import reference
from rfp_agent.pipeline.run import RunContext, create_run, execute_run
from tests.docx_factory import build_gis_spec, build_judgment_spec

VERSION = "test-dict-v1"


def run_once(conn, path):
    run_id = create_run(conn, VERSION, None)
    assert execute_run(RunContext(conn, VERSION, None, None), run_id, [path]) == "ENGINEER_REVIEW"
    return run_id


def test_filter_by_family(db):
    """Scenario: 제품군으로 거르기 — GIS 제품만 오고 주요 칸과 빈 칸 수가 있다."""
    rows = reference.products(db, family="GIS", limit=500)
    assert rows and {r["family"] for r in rows} == {"GIS"}
    assert reference.count_products(db, family="GIS") == len(rows)
    for key in ("rated_voltage_kv", "rated_current_a", "short_circuit_ka", "rated_frequency",
                "empty_count"):
        assert key in rows[0]
    assert [r["product_code"] for r in rows] == sorted(r["product_code"] for r in rows)
    hit = reference.products(db, q=rows[0]["product_code"].lower())
    assert rows[0]["product_code"] in [r["product_code"] for r in hit]


def test_empty_value_stays_empty(db):
    """Scenario: 빈 칸은 비어 있음 — 판정에 쓰는 칸이 비면 빈 값으로 오고 빈 칸 수에 들어간다."""
    rows = reference.products(db, limit=500)
    empty = next(r for r in rows if r["empty_count"])
    for col in empty["empty_columns"]:
        assert empty[col] is None
    full = reference.product(db, empty["product_code"])
    assert full["empty_count"] == empty["empty_count"]
    assert all(full[c] is None for c in full["empty_columns"])


def test_assumed_loss(db):
    """Scenario: 팀 가정 손실값 — 손실값과 팀 가정 표시가 함께 온다."""
    rows = reference.products(db, limit=500)
    trf = next(r for r in rows if r["loss_is_assumed"])
    assert trf["noload_loss_kw"] is not None or trf["load_loss_kw"] is not None
    fams = {f["family"]: f for f in reference.families(db)}
    assert fams[trf["family"]]["assumed"] >= 1


def test_product_used_in_judgments(db, tmp_path):
    """Scenario: 판정에 쓰인 제품 — 현재 판정 수와 실행 번호·항목·결과가 온다."""
    run_id = run_once(db, build_judgment_spec(tmp_path / "synthetic_judgment.docx"))
    code, n = db.execute(
        "SELECT product_code, count(*) FROM judgment WHERE run_id = %s AND is_current "
        "AND product_code IS NOT NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 1", (run_id,)).fetchone()
    p = reference.product(db, code)
    assert p["used"] == n and len(p["used_in"]) == n
    assert {u["run_id"] for u in p["used_in"]} == {run_id}
    assert all(u["item_name"] and u["result"] and u["review_no"].startswith("RV-")
               for u in p["used_in"])
    listed = next(r for r in reference.products(db, q=code) if r["product_code"] == code)
    assert listed["used"] == n


def test_product_use_item_and_due(db, tmp_path):
    """Scenario: 쓰인 판정의 표준 항목과 마감 — 정격 전류 판정 줄에 rated_current와 검토 마감."""
    from datetime import date

    run_id = run_once(db, build_judgment_spec(tmp_path / "synthetic_judgment.docx"))
    db.execute("UPDATE review_run SET due_date = '2026-11-20' WHERE run_id = %s", (run_id,))
    code = db.execute(
        "SELECT j.product_code FROM judgment j JOIN req_value v USING (value_id) "
        "WHERE j.run_id = %s AND j.is_current AND v.item_key = 'rated_current' "
        "AND j.product_code IS NOT NULL LIMIT 1", (run_id,)).fetchone()[0]
    rows = [u for u in reference.product(db, code)["used_in"] if u["item_key"] == "rated_current"]
    assert rows and all(u["due_date"] == date(2026, 11, 20) for u in rows)


def test_product_not_used(db):
    """Scenario: 쓰이지 않은 제품 — 판정에 쓰인 수 0, 목록 비어 있음. 없는 제품은 찾을 수 없음."""
    code = reference.products(db, limit=1)[0]["product_code"]
    p = reference.product(db, code)
    assert p["used"] == 0 and p["used_in"] == []
    with pytest.raises(reference.NotFound):
        reference.product(db, "NO-SUCH-PRODUCT")


def test_compare_rule_dictionary(db, tmp_path):
    """Scenario: 비교 방향 사전 — 적재된 줄이 방향·시간 조건과 쓴 판정 수와 함께 온다."""
    rules = reference.compare_rules(db)
    assert len(rules) == 39
    assert {"table_name", "item_no", "item_key", "direction", "time_condition",
            "strength_direction", "used"} <= set(rules[0])
    run_id = run_once(db, build_judgment_spec(tmp_path / "synthetic_judgment.docx"))
    used = {r["compare_rule_id"]: r["used"] for r in reference.compare_rules(db)}
    for rule_id, n in db.execute(
            "SELECT compare_rule_id, count(*) FROM judgment WHERE run_id = %s AND is_current "
            "AND compare_rule_id IS NOT NULL GROUP BY 1", (run_id,)):
        assert used[rule_id] == n


def test_risk_expression_usage(db, tmp_path):
    """Scenario: 위험 표현이 쓰인 횟수 — 그 표현으로 찾은 후보 수가 쓴 횟수다."""
    run_id = run_once(db, build_gis_spec(tmp_path / "synthetic_154kV_GIS_spec.docx"))
    rows = reference.risk_expressions(db)
    [row] = [r for r in rows if r["expression"] == "including but not limited to"]
    n = db.execute("SELECT count(*) FROM risk_flag WHERE run_id = %s AND expr_id = %s",
                   (run_id, row["expr_id"])).fetchone()[0]
    assert n >= 1 and row["used"] == n


def test_item_aliases(db):
    """Scenario: 같은 뜻 표현 — 표준 항목마다 이름, 방향, 같은 뜻 표현 목록이 온다."""
    rows = reference.items(db)
    current = next(r for r in rows if r["item_key"] == "rated_current")
    assert current["name_ko"] and current["default_direction"] and current["strength_direction"]
    assert current["aliases"] and all(isinstance(a, str) for a in current["aliases"])
    assert current["pm_column"] == "rated_current_a" and current["used"] >= 0


def test_reference_api(db, db_url, monkeypatch):
    """읽기 API: 목록 머리글 X-Total-Count, 없는 제품 404, 규칙 사전 네 가지."""
    from fastapi.testclient import TestClient

    from rfp_agent.api.main import app
    from rfp_agent.config import get_settings

    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    get_settings.cache_clear()
    try:
        client = TestClient(app)
        res = client.get("/api/products", params={"family": "GIS", "limit": 2})
        assert res.status_code == 200 and len(res.json()) == 2
        assert int(res.headers["X-Total-Count"]) >= 2
        assert client.get("/api/products/families").json()
        assert client.get("/api/products/NO-SUCH").status_code == 404
        for path in ("/api/rules/compare", "/api/rules/items", "/api/rules/risk-expressions",
                     "/api/rules/doc-kinds"):
            assert client.get(path).json()
    finally:
        get_settings.cache_clear()


def test_assumed_comparison_values(db):
    """Scenario: 팀 가정 비교값 — 비교값 팀 가정 표시가 오고 제품군 팀 가정 수에 셈된다."""
    rows = reference.products(db, family="GIS", limit=500)
    gis = next(r for r in rows if r["comparison_values_assumed"] is True)
    assert not gis["is_assumed"] and not gis["loss_is_assumed"]
    fams = {f["family"]: f for f in reference.families(db)}
    assert fams["GIS"]["assumed"] >= 1
