"""문서 읽기 점검과 그림 위치 기록.

명세 review-run·document-intake의 Scenario (change update-review-screens).
"""

import pytest

from rfp_agent.pipeline import read_checks, review
from rfp_agent.pipeline.docx_reader import find_figures, read_blocks
from rfp_agent.pipeline.run import RunContext, create_run, execute_run
from tests.docx_factory import build_read_spec

VERSION = "test-dict-v1"


@pytest.fixture
def read_spec(tmp_path):
    return build_read_spec(tmp_path / "synthetic_judgment.docx")


@pytest.fixture
def run(db, read_spec):
    run_id = create_run(db, VERSION, None)
    assert execute_run(RunContext(db, VERSION, None, None), run_id, [read_spec]) \
        == "ENGINEER_REVIEW"
    return run_id


def test_figure_location(db, run, read_spec):
    """Scenario: 단선도 그림 위치."""
    figures = find_figures(read_blocks(read_spec))
    assert [c for _, c in figures] == ["Fig. 1 Single Line Diagram"]
    line = figures[0][0].line_no
    stored = db.execute(
        "SELECT f.line_no, f.caption FROM doc_figure f JOIN run_document rd USING (document_id) "
        "WHERE rd.run_id = %s", (run,)).fetchall()
    assert stored == [(line, "Fig. 1 Single Line Diagram")]
    texts = [r[0] for r in db.execute(
        "SELECT q.text_raw FROM requirement q JOIN run_document rd USING (document_id) "
        "JOIN requirement_location ql USING (requirement_id) "
        "JOIN source_location l USING (location_id) WHERE rd.run_id = %s AND l.line_start = %s",
        (run, line))]
    assert texts == []


def test_read_check_list(db, run):
    """Scenario: 읽지 못한 곳 목록."""
    rows = read_checks.read_checks(db, run)
    kinds = [r["kind"] for r in rows]
    assert kinds == sorted(kinds, key=read_checks.KINDS.index)
    assert set(kinds) == set(read_checks.KINDS)
    for r in rows:
        assert r["file_name"] == "synthetic_judgment.docx" and r["todo"] and r["problem"]
        assert r["checked_by"] is None and r["checked_at"] is None
    by_kind = {r["kind"]: r for r in rows}
    assert "Fig. 1 Single Line Diagram" in by_kind["그림"]["loc"]
    assert by_kind["단위"]["loc"] == "TS-115-GIS-B · No. 11~12"
    assert "\"1.2\"" in by_kind["단위"]["problem"]
    place = next(r for r in rows if r["what"] == "위치가 모호함")
    assert place["loc"].startswith("2.1절 · ") and "행과 " in place["loc"]
    assert all("행" in r["loc"] for r in rows if r["kind"] != "단위")
    assert read_checks.read_checks(db, run) == rows                 # 같은 입력, 같은 결과 (CR-11)


def test_check_and_undo(db, run):
    """Scenario: 점검 확인과 되돌리기."""
    engineer = review.default_user(db, "ENGINEER")
    first = read_checks.read_checks(db, run)[0]
    left = read_checks.unchecked(db, run)
    done = read_checks.set_checked(db, run, first["key"], True, engineer)
    assert done["checked_by"] and done["checked_at"] is not None
    assert read_checks.unchecked(db, run) == left - 1
    with pytest.raises(review.ReviewError) as again:
        read_checks.set_checked(db, run, first["key"], True, engineer)
    assert again.value.status == 409
    undone = read_checks.set_checked(db, run, first["key"], False, engineer)
    assert undone["checked_by"] is None and undone["checked_at"] is None
    assert read_checks.unchecked(db, run) == left
    log = review.history(db, run, target="read_check")
    assert [entry["action"] for entry in log] == ["CONFIRM", "UNDO"]
    assert {entry["target_label"] for entry in log} == {f"{first['loc']} ({first['what']})"}


def test_check_only_in_review(db, run):
    """Scenario: 담당자 확인 단계에서만 확인."""
    key = read_checks.read_checks(db, run)[0]["key"]
    review.finish_review(db, run, review.default_user(db, "APPROVER"), "점검은 결재자 확인")
    with pytest.raises(review.ReviewError) as exc:
        read_checks.set_checked(db, run, key, True)
    assert exc.value.status == 409


def test_read_checks_api(db, run, db_url, monkeypatch):
    """점검 목록·확인·되돌리기 API와 승인 화면의 미확인 수."""
    from fastapi.testclient import TestClient

    from rfp_agent.api.main import app
    from rfp_agent.config import get_settings

    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    get_settings.cache_clear()
    try:
        client = TestClient(app)
        url = f"/api/runs/{run}"
        rows = client.get(f"{url}/read-checks").json()
        left = client.get(f"{url}/approval").json()["read_unchecked"]
        assert left == len(rows)
        key = rows[0]["key"]
        assert client.post(f"{url}/read-checks/{key}", json={}).json()["checked_by"]
        assert client.get(f"{url}/approval").json()["read_unchecked"] == left - 1
        assert client.delete(f"{url}/read-checks/{key}").json()["checked_at"] is None
        assert client.post(f"{url}/read-checks/X-0", json={}).status_code == 404
        assert client.get("/api/runs/999999/read-checks").status_code == 404
    finally:
        get_settings.cache_clear()
