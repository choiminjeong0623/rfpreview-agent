"""데이터시트 채우기. 명세 bid-outputs "데이터시트 채우기"의 Scenario (add-datasheet-export)."""

from io import BytesIO

import pytest
from openpyxl import load_workbook

from rfp_agent.pipeline import datasheet, queries, review
from rfp_agent.pipeline.run import RunContext, create_run, execute_run

VERSION = "test-dict-v1"


def run_once(conn, paths):
    run_id = create_run(conn, VERSION, None)
    assert execute_run(RunContext(conn, VERSION, None, None), run_id, paths) == "ENGINEER_REVIEW"
    return run_id


def sheet(conn, run_id, name):
    [s] = [s for s in datasheet.datasheets(conn, run_id) if s["table_name"] == name]
    return datasheet.datasheet(conn, run_id, s["table_id"])


def test_datasheet_warranty_row(db, spec):
    """Scenario: 보증값 후보 칸 — LS ELECTRIC, 회사 고정값, 후보."""
    run_id = run_once(db, [spec])
    rows = {r["item_en"]: r for r in sheet(db, run_id, "TS-115-GIS")["rows"]}
    maker = rows["Manufacturer's name"]
    assert (maker["value"], maker["basis"], maker["status"], maker["target"]) == (
        "LS ELECTRIC", "회사 고정값", "후보", "warranty")
    assert maker["no"] == "7" and maker["requirement"] == "—"


def test_datasheet_empty_row(db, spec):
    """Scenario: 근거 없는 빈 칸 — 채운 값 없음, 확인 필요, 이유."""
    run_id = run_once(db, [spec])
    names = {s["table_name"] for s in datasheet.datasheets(db, run_id)}
    rows = [r for n in names for r in sheet(db, run_id, n)["rows"]]
    empty = [r for r in rows if r["state"] == "empty"]
    assert empty and all(r["value"] is None and r["status"] == "확인 필요" and r["why"]
                         for r in empty)
    weight = next(r for r in rows if r["item_en"] == "Weight of circuit breaker")
    assert weight["state"] == "empty" and "제품표에 값이 없음" in weight["why"]


def test_datasheet_judged_row(db, spec):
    """Scenario: 판정 제품값 칸 — 확정한 판정은 제품값(제품 코드), 확정."""
    run_id = run_once(db, [spec])
    j = next(j for j in queries.run_judgments(db, run_id, limit=500)
             if j["result"] == "COMPLY" and j["product_value_raw"])
    review.act(RunContext(db, VERSION, None, None), run_id, "judgment", j["judgment_id"],
               "CONFIRM")
    table = j["locations"][0]["table_name"]
    row = next(r for r in sheet(db, run_id, table)["rows"] if r["judgment_id"] == j["judgment_id"])
    assert row["value"].startswith(j["product_value_raw"]) and f"({j['product_code']})" in row[
        "value"]
    assert (row["status"], row["target"]) == ("확정", "judgment")


def test_datasheet_xlsx(db, spec):
    """Scenario: 데이터시트 엑셀 — 파일 이름, 줄 수와 칸 순서가 화면과 같다."""
    run_id = run_once(db, [spec])
    data = sheet(db, run_id, "TS-115-GIS")
    name, body, n = datasheet.datasheet_xlsx(db, run_id, data["table_id"])
    assert name == f"Datasheet_TS-115-GIS_{data['review_no']}.xlsx" == data["file_name"]
    ws = load_workbook(BytesIO(body)).active
    values = [list(r) for r in ws.iter_rows(values_only=True)]
    head = values.index(datasheet.HEADER)
    assert [v[0] for v in values[head + 1:]] == [r["no"] for r in data["rows"]]
    assert n == len(data["rows"]) == data["counts"]["rows"]


def test_datasheet_not_in_run(db, spec):
    """다른 실행의 표는 없음."""
    run_id = run_once(db, [spec])
    with pytest.raises(datasheet.NotFound):
        datasheet.datasheet(db, run_id, -1)


def test_datasheet_api(db, db_url, spec, monkeypatch):
    """데이터시트 API: 목록, 한 장, 엑셀, 없는 표 404."""
    from fastapi.testclient import TestClient

    from rfp_agent.api.main import app
    from rfp_agent.config import get_settings

    run_id = run_once(db, [spec])
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    get_settings.cache_clear()
    try:
        client = TestClient(app)
        sheets = client.get(f"/api/runs/{run_id}/datasheets").json()
        assert sheets and all(s["rows"] > 0 for s in sheets)
        tid = sheets[0]["table_id"]
        assert client.get(f"/api/runs/{run_id}/datasheet", params={"table_id": tid}).json()["rows"]
        res = client.get(f"/api/runs/{run_id}/datasheet/export", params={"table_id": tid})
        assert res.status_code == 200 and int(res.headers["X-Row-Count"]) == sheets[0]["rows"]
        assert client.get(f"/api/runs/{run_id}/datasheet",
                          params={"table_id": -1}).status_code == 404
    finally:
        get_settings.cache_clear()
