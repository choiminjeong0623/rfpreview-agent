"""제품표 엑셀 내보내기 (add-product-export). 명세 reference-data "제품표 내보내기"의 Scenario."""

from io import BytesIO

from openpyxl import load_workbook

from rfp_agent.pipeline import reference
from rfp_agent.pipeline.product_export import COLUMNS, products_xlsx

HEAD_ROW = 4


def _sheet(body: bytes):
    ws = load_workbook(BytesIO(body)).active
    head = [c.value for c in ws[HEAD_ROW]]
    data = [dict(zip(head, r, strict=True)) for r in ws.iter_rows(min_row=HEAD_ROW + 1,
                                                                   values_only=True)]
    return ws, head, data


def test_export_same_filter_as_list(db):
    """Scenario: 거른 제품 내보내기 — GIS로 거르면 목록과 같은 제품이 같은 순서로 온다."""
    name, body, n = products_xlsx(db, family="GIS")
    listed = reference.products(db, family="GIS", limit=500)
    ws, head, data = _sheet(body)
    assert name == "제품표_GIS.xlsx" and n == len(listed) == len(data)
    assert [r["제품 코드"] for r in data] == [p["product_code"] for p in listed]
    assert "제품군 GIS" in ws["A1"].value and f"제품 {n}개" in ws["A1"].value
    assert head[: len(COLUMNS)] == [h for _, h in COLUMNS]
    hit = products_xlsx(db, q=listed[0]["product_code"].lower())[2]
    assert hit >= 1


def test_export_keeps_empty_cells(db):
    """Scenario: 빈 칸은 비워 둠 — 제품표에서 빈 칸은 엑셀에서도 빈 셀이다 (CR-04)."""
    empty = next(r for r in reference.products(db, limit=500) if r["empty_count"])
    _, _, data = _sheet(products_xlsx(db, q=empty["product_code"])[1])
    row = next(r for r in data if r["제품 코드"] == empty["product_code"])
    labels = dict(COLUMNS)
    for col in empty["empty_columns"]:
        assert row[labels[col]] is None


def test_export_marks_team_assumption(db):
    """Scenario: 팀 가정 표시 — 팀 합성 비교값 제품은 "팀 가정" 칸에 "비교값", 줄 색 (CR-06)."""
    gis = next(r for r in reference.products(db, family="GIS", limit=500)
               if r["comparison_values_assumed"])
    ws, _, data = _sheet(products_xlsx(db, family="GIS")[1])
    i, row = next((i, r) for i, r in enumerate(data) if r["제품 코드"] == gis["product_code"])
    assert "비교값" in row["팀 가정"]
    assert ws.cell(row=HEAD_ROW + 1 + i, column=1).fill.fgColor.rgb.endswith("EFF8FF")


def test_export_is_reproducible(db):
    """같은 제품표면 같은 내용 (CR-11): 내보낸 시각을 넣지 않는다."""
    a, b = products_xlsx(db)[1], products_xlsx(db)[1]
    assert [list(r) for r in load_workbook(BytesIO(a)).active.values] == \
        [list(r) for r in load_workbook(BytesIO(b)).active.values]


def test_export_api(db, db_url, monkeypatch):
    """내보내기 API: 엑셀 형식, 한글 파일 이름, X-Row-Count."""
    from fastapi.testclient import TestClient

    from rfp_agent.api.main import app
    from rfp_agent.config import get_settings

    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    get_settings.cache_clear()
    try:
        res = TestClient(app).get("/api/products/export", params={"family": "GIS"})
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("application/vnd.openxmlformats")
        assert "%EC%A0%9C%ED%92%88%ED%91%9C_GIS.xlsx" in res.headers["content-disposition"]
        assert int(res.headers["X-Row-Count"]) == reference.count_products(db, family="GIS")
    finally:
        get_settings.cache_clear()
