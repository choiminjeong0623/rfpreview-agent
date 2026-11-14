"""원문 앞뒤 줄 API (판정 상세 화면).

명세 evidence-integrity "원문 앞뒤 줄"의 Scenario (change add-judgment-view).
"""

import pytest
from fastapi.testclient import TestClient

from rfp_agent.pipeline import queries, source_lines
from rfp_agent.pipeline.run import RunContext, create_run, execute_run
from tests.docx_factory import build_gis_spec

VERSION = "test-dict-v1"


@pytest.fixture
def client(db, db_url, monkeypatch):
    from rfp_agent.api.main import app
    from rfp_agent.config import get_settings

    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    get_settings.cache_clear()
    yield TestClient(app)
    get_settings.cache_clear()


@pytest.fixture
def run(db, spec):
    run_id = create_run(db, VERSION, None)
    assert execute_run(RunContext(db, VERSION, None, None), run_id, [spec]) == "ENGINEER_REVIEW"
    return run_id


def _lines(client, run_id, file_no, start, end):
    return client.get(f"/api/runs/{run_id}/documents/{file_no}/lines",
                      params={"from": start, "to": end})


def test_lines_around_location(db, run, client):
    """Scenario: 원문 위치 앞뒤 줄."""
    j = queries.run_judgments(db, run, result="DEVIATION_CANDIDATE")[0]
    loc = j["locations"][0]
    at = loc["line_start"]
    res = _lines(client, run, loc["file_no"], at - 2, at + 2)
    assert res.status_code == 200
    body = res.json()
    assert body["partial"] is False and body["file_name"].endswith(".docx")
    assert [x["line_no"] for x in body["lines"]] == list(range(at - 2, at + 3))
    hit = next(x["text"] for x in body["lines"] if x["line_no"] == at)
    assert j["req_value_raw"] in hit and j["item_name_raw"] in hit


def test_sentence_line_matches_requirement(db, seeded_db, tmp_path, client):
    """Scenario: 원문 위치 앞뒤 줄 (문장 요구사항은 그 줄 글이 요구 문장이다)."""
    path = build_gis_spec(tmp_path / "gis_spec.docx")
    run_id = create_run(db, VERSION, None)
    execute_run(RunContext(db, VERSION, None, None), run_id, [path])
    reqs = [r for r in queries.run_requirements(db, run_id, limit=500)
            if r["source_kind"] == "SENTENCE" and r["locations"]]
    assert reqs
    r = reqs[0]
    loc = r["locations"][0]
    body = _lines(client, run_id, loc["file_no"], loc["line_start"], loc["line_start"]).json()
    assert body["lines"][0]["text"].strip() == r["text_raw"].strip()


def test_stored_lines_when_file_missing(db, run, spec, client):
    """Scenario: 파일이 없으면 저장된 줄만."""
    j = queries.run_judgments(db, run, result="DEVIATION_CANDIDATE")[0]
    loc = j["locations"][0]
    at = loc["line_start"]
    spec.unlink()
    body = _lines(client, run, loc["file_no"], at - 2, at + 2).json()
    assert body["partial"] is True
    by_no = {x["line_no"]: x["text"] for x in body["lines"]}
    # 표 행은 칸을 " | "로 잇는다
    assert j["req_value_raw"] in by_no[at] and " | " in by_no[at]
    assert all(at - 2 <= n <= at + 2 for n in by_no)


def test_line_range_limit(db, run, client):
    """Scenario: 줄 범위 제한."""
    file_no = queries.run_documents(db, run)[0]["file_no"]
    assert _lines(client, run, file_no, 1, 41).status_code == 400
    assert _lines(client, run, file_no, 10, 9).status_code == 400
    assert _lines(client, run, file_no, 0, 3).status_code == 400
    ok = _lines(client, run, file_no, 1, source_lines.MAX_LINES)
    assert ok.status_code == 200 and len(ok.json()["lines"]) <= source_lines.MAX_LINES


def test_document_not_in_run(db, run, client):
    """Scenario: 검토에 없는 문서."""
    res = _lines(client, run, 999, 1, 5)
    assert res.status_code == 404 and "파일 999" in res.json()["detail"]
