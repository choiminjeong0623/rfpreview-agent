"""TBE 준수표. 명세 bid-outputs "TBE 준수표"의 Scenario (add-tbe-export)."""

from io import BytesIO

from openpyxl import load_workbook

from rfp_agent.pipeline import queries, review, tbe
from rfp_agent.pipeline.run import RunContext, create_run, execute_run

VERSION = "test-dict-v1"


def run_once(conn, paths):
    run_id = create_run(conn, VERSION, None)
    assert execute_run(RunContext(conn, VERSION, None, None), run_id, paths) == "ENGINEER_REVIEW"
    return run_id


def deviation_confirmed(conn, spec):
    """판정 하나를 일탈 후보로 고쳐(= 확정) 나머지는 후보로 둔다."""
    run_id = run_once(conn, [spec])
    j = next(j for j in queries.run_judgments(conn, run_id, limit=500) if j["result"] == "COMPLY")
    review.act(RunContext(conn, VERSION, None, None), run_id, "judgment", j["judgment_id"], "EDIT",
               {"result": "DEVIATION_CANDIDATE"}, "시험용 일탈")
    return run_id, j["judgment_id"]


def test_tbe_with_candidates(db, spec):
    """Scenario: 후보 포함 — 첫 줄 Deviation·확정, 나머지 후보, 보증값 작성 없음."""
    run_id, jid = deviation_confirmed(db, spec)
    data = tbe.tbe(db, run_id)
    rows = data["rows"]
    assert rows[0]["judgment_id"] == jid
    assert (rows[0]["verdict"], rows[0]["status"]) == ("Deviation", "Confirmed")
    assert all(r["status"].startswith("Candidate") for r in rows[1:])
    assert all(r["result"] != "WARRANTY_TO_FILL" for r in rows)
    assert {r["verdict"] for r in rows} <= {"Comply", "Deviation", "Clarification",
                                            "To be confirmed"}
    assert data["counts"]["rows"] == len(rows) and data["counts"]["no_location"] == 0
    assert data["counts"]["candidates"] == len(rows) - 1
    assert all(r["file_name"] and r["source"] for r in rows)        # 원문 위치 (CR-03)
    assert data == tbe.tbe(db, run_id)                               # 같은 입력 같은 결과


def test_tbe_confirmed_only(db, spec):
    """Scenario: 확정한 줄만 — 확정한 판정만."""
    run_id, jid = deviation_confirmed(db, spec)
    data = tbe.tbe(db, run_id, include="confirmed")
    assert [r["judgment_id"] for r in data["rows"]] == [jid]
    assert data["file_name"].endswith("_확정만.xlsx")


def test_tbe_xlsx(db, spec):
    """Scenario: 엑셀 파일 — 이름, 머리 줄, 줄 수가 미리보기와 같다."""
    run_id, _ = deviation_confirmed(db, spec)
    name, body, n = tbe.tbe_xlsx(db, run_id)
    review_no = queries.run_summary(db, run_id)["review_no"]
    assert name == f"TBE_{review_no}_후보포함.xlsx"
    ws = load_workbook(BytesIO(body)).active
    values = [list(r) for r in ws.iter_rows(values_only=True)]
    head = values.index(["No.", "Item", "Requirement", "Compliance", "Offered", "Source", "Status"])
    assert len(values) - head - 1 == n == len(tbe.tbe(db, run_id)["rows"])
    assert values[head + 1][3] == "Deviation"


def test_tbe_language(db, spec):
    """Scenario: 항목 언어 — 국문이면 한글 이름과 국문 준수 여부."""
    run_id, _ = deviation_confirmed(db, spec)
    en = tbe.tbe(db, run_id)["rows"]
    ko = tbe.tbe(db, run_id, lang="ko")["rows"]
    judged = {j["judgment_id"]: j for j in queries.run_judgments(db, run_id, limit=500)}
    for r in ko:
        j = judged[r["judgment_id"]]
        assert r["item"] == (j["item_name"] or j["item_name_raw"] or j["item_key"])
    assert {r["verdict"] for r in ko} <= {"준수", "일탈", "질의", "확인 필요"}
    assert ko[0]["status"] == "확정" and [r["judgment_id"] for r in ko] == [
        r["judgment_id"] for r in en]
    both = tbe.tbe(db, run_id, lang="both")["rows"]
    assert both[0]["item"] == en[0]["item"] and both[0]["item_ko"] == ko[0]["item"]


def test_tbe_api(db, db_url, spec, monkeypatch):
    """TBE API: 미리보기, 엑셀 머리글, 승인 전 제출본 v1은 409."""
    from fastapi.testclient import TestClient

    from rfp_agent.api.main import app
    from rfp_agent.config import get_settings

    run_id, _ = deviation_confirmed(db, spec)
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    get_settings.cache_clear()
    try:
        client = TestClient(app)
        res = client.get(f"/api/runs/{run_id}/tbe", params={"include": "confirmed"})
        assert res.status_code == 200 and res.json()["counts"]["rows"] == 1
        res = client.get(f"/api/runs/{run_id}/tbe/export")
        assert res.status_code == 200 and res.headers["X-Row-Count"].isdigit()
        assert "attachment" in res.headers["Content-Disposition"]
        assert client.get(f"/api/runs/{run_id}/tbe", params={"base": "v1"}).status_code == 409
        assert client.get(f"/api/runs/{run_id}/tbe", params={"lang": "jp"}).status_code == 422
    finally:
        get_settings.cache_clear()
