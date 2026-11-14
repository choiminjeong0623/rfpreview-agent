"""판정 목록 거르기·판정 순서·칩 건수·위험 조건 항목 이름.

명세 review-run의 Scenario (change update-review-screens).
"""

import pytest

from rfp_agent.pipeline import queries, review
from rfp_agent.pipeline.loss import recalculate
from rfp_agent.pipeline.run import RunContext, create_run, execute_run
from tests.docx_factory import build_gis_spec

VERSION = "test-dict-v1"
ORDER = ["DEVIATION_CANDIDATE", "QUERY_CANDIDATE", "NEEDS_REVIEW", "WARRANTY_TO_FILL", "COMPLY"]


@pytest.fixture
def run(db, spec):
    run_id = create_run(db, VERSION, None)
    assert execute_run(RunContext(db, VERSION, None, None), run_id, [spec]) == "ENGINEER_REVIEW"
    return run_id


def test_unconfirmed_deviations_only(db, run):
    """Scenario: 확정 안 한 일탈 후보만."""
    devs = queries.run_judgments(db, run, result="DEVIATION_CANDIDATE")
    assert len(devs) == 4
    review.act(RunContext(db, VERSION, None, None), run, "judgment", devs[0]["judgment_id"],
               "CONFIRM")
    left = queries.run_judgments(db, run, result="DEVIATION_CANDIDATE", unconfirmed=True)
    assert len(left) == 3 and devs[0]["judgment_id"] not in [j["judgment_id"] for j in left]
    assert queries.count_judgments(db, run, result="DEVIATION_CANDIDATE", unconfirmed=True) == 3


def test_priority_order(db, run):
    """Scenario: 판정 순서로 받기."""
    rows = queries.run_judgments(db, run, priority=True, limit=500)
    ranks = [ORDER.index(j["result"]) for j in rows]
    assert ranks == sorted(ranks) and rows[0]["result"] == "DEVIATION_CANDIDATE"
    assert rows[-1]["result"] == "COMPLY"
    assert all("type_name" in j for j in rows)


def test_search_filter(db, run):
    """Scenario: 검색어로 거르기."""
    rows = queries.run_judgments(db, run, q="busbar", limit=500)
    assert rows and all("busbar" in (j["item_name_raw"] or "").lower() for j in rows)
    assert queries.count_judgments(db, run, q="BUSBAR") == len(rows)
    assert queries.run_judgments(db, run, q="없는검색어") == []


def test_chip_counts(db, run):
    """Scenario: 칩 건수."""
    counts = queries.judgment_counts(db, run)
    assert sum(counts["by_result"].values()) == counts["total"]
    assert counts["total"] == queries.count_judgments(db, run)
    assert counts["unconfirmed"] == counts["total"]
    j = queries.run_judgments(db, run, result="COMPLY")[0]
    review.act(RunContext(db, VERSION, None, None), run, "judgment", j["judgment_id"], "CONFIRM")
    after = queries.judgment_counts(db, run)
    assert after["unconfirmed"] == counts["total"] - 1
    assert after["unconfirmed_comply"] == counts["unconfirmed_comply"] - 1


def test_judgment_filters_api(db, run, db_url, monkeypatch):
    """판정 목록 API의 거르기·정렬과 칩 건수 API."""
    from fastapi.testclient import TestClient

    from rfp_agent.api.main import app
    from rfp_agent.config import get_settings

    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    get_settings.cache_clear()
    try:
        client = TestClient(app)
        url = f"/api/runs/{run}"
        res = client.get(f"{url}/judgments", params={"order": "priority", "limit": 3,
                                                     "unconfirmed": "true"})
        assert res.status_code == 200 and res.headers["X-Total-Count"]
        assert res.json()[0]["result"] == "DEVIATION_CANDIDATE"
        assert client.get(f"{url}/judgments", params={"order": "name"}).status_code == 422
        counts = client.get(f"{url}/judgment-counts").json()
        assert counts["by_result"]["DEVIATION_CANDIDATE"] == 4
    finally:
        get_settings.cache_clear()


def test_mismatch_item_name(seeded_db, tmp_path):
    """Scenario: 값 불일치 항목 이름."""
    run_id = create_run(seeded_db, VERSION, None)
    path = build_gis_spec(tmp_path / "synthetic_154kV_GIS_spec.docx")
    ctx = RunContext(seeded_db, VERSION, None, None)
    assert execute_run(ctx, run_id, [path]) == "ENGINEER_REVIEW"
    names = {r["risk_kind"]: r["item_name"] for r in queries.run_risks(seeded_db, run_id)}
    assert names["VALUE_MISMATCH"] == "가스 누설률"
    assert names["BLANKET"] is None


def test_loss_amounts(db, tmp_path):
    """Scenario: 종류별 가산액과 단가 위치."""
    from tests.docx_factory import build_loss_spec

    run_id = create_run(db, VERSION, None)
    path = build_loss_spec(tmp_path / "synthetic_judgment_loss.docx")
    assert execute_run(RunContext(db, VERSION, None, None), run_id, [path]) == "ENGINEER_REVIEW"
    [loss] = queries.run_losses(db, run_id)
    assert loss["amounts"] == {"noload": None, "load": None, "aux": None}
    assert [p["item_no"] for p in loss["price_locations"]] == ["3", "4", "5"]
    recalculate(db, loss["loss_calc_id"], 60, 300, 8)
    [loss] = queries.run_losses(db, run_id)
    assert loss["amounts"] == {"noload": 270_000, "load": 960_000, "aux": 10_400}
    assert float(loss["total_usd"]) == sum(loss["amounts"].values())


def test_history_target_labels(db, run, tmp_path):
    """Scenario: 이력 대상 이름."""
    ctx = RunContext(db, VERSION, None, None)
    [j] = queries.run_judgments(db, run, result="QUERY_CANDIDATE", limit=1)
    review.act(ctx, run, "judgment", j["judgment_id"], "EDIT", {"result": "COMPLY"}, "회신 확인")
    log = review.history(db, run)
    assert log[-1]["target_label"] == (j["item_name"] or j["item_name_raw"])

    other = create_run(db, VERSION, None)
    execute_run(ctx, other, [build_gis_spec(tmp_path / "synthetic_154kV_GIS_spec.docx")])
    blanket = next(r for r in queries.run_risks(db, other) if r["risk_kind"] == "BLANKET")
    review.act(ctx, other, "risk_flag", blanket["risk_id"], "REJECT", reason="일반 조항")
    assert review.history(db, other)[-1]["target_label"] == blanket["expression"]


def test_deviation_list_docx(db, run, db_url, monkeypatch):
    """Scenario: 넣을 항목이 없는 초안 · Scenario: 일탈 목록 초안 Word 파일."""
    from io import BytesIO

    from docx import Document
    from fastapi.testclient import TestClient

    from rfp_agent.api.main import app
    from rfp_agent.config import get_settings

    items = queries.run_outputs(db, run, "DEVIATION")
    removed = items[0]
    review.act(RunContext(db, VERSION, None, None), run, "output_item", removed["item_id"],
               "REJECT", reason="목록에서 뺌")
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    get_settings.cache_clear()
    try:
        res = TestClient(app).get(f"/api/runs/{run}/outputs/export?list_kind=DEVIATION")
        assert res.status_code == 200
        assert "filename*=UTF-8''" in res.headers["content-disposition"]
        doc = Document(BytesIO(res.content))
        assert doc.paragraphs[0].text == "일탈 목록 초안"
        rows = doc.tables[0].rows
        assert [c.text for c in rows[0].cells] == ["No.", "원문 위치", "문장", "상태"]
        assert len(rows) - 1 == len(items) - 1          # 뺀 항목은 넣지 않는다
        assert all("행" in r.cells[1].text for r in rows[1:])
        assert removed["text_draft"] not in [r.cells[2].text for r in rows[1:]]
        assert TestClient(app).get(f"/api/runs/{run}/outputs/export?list_kind=X").status_code == 422
        # 목록에 올릴 항목을 모두 빼면 빈 파일을 만들지 않는다
        for item in items[1:]:
            review.act(RunContext(db, VERSION, None, None), run, "output_item", item["item_id"],
                       "REJECT", reason="목록에서 뺌")
        empty = TestClient(app).get(f"/api/runs/{run}/outputs/export?list_kind=DEVIATION")
        assert empty.status_code == 409
        assert "후보가 없습니다" in empty.json()["detail"]
    finally:
        get_settings.cache_clear()
