"""분석 전 분류 추천과 사람이 정한 문서 분류.

명세 document-intake(add-document-confirm)의 Scenario.
"""

import json

import pytest

from rfp_agent.pipeline import queries
from rfp_agent.pipeline.run import RunContext, create_run, execute_run
from tests.docx_factory import build_judgment_spec

VERSION = "test-dict-v1"
IEC_TITLE = "SCHEDULE OF TECHNICAL DATA (IEC 62271-1, IEC 62271-203, IEC 60376)"


def run_once(conn, paths, choices=None):
    run_id = create_run(conn, VERSION, None)
    assert execute_run(RunContext(conn, VERSION, None, None), run_id, paths,
                       choices) == "ENGINEER_REVIEW"
    return run_id


def count(conn, table):
    return conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


@pytest.fixture
def client(db, db_url, monkeypatch):
    from fastapi.testclient import TestClient

    from rfp_agent.api.main import app
    from rfp_agent.config import get_settings

    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    get_settings.cache_clear()
    yield TestClient(app)
    get_settings.cache_clear()


def preview(client, *paths):
    files = [("files", (p.name, p.read_bytes())) for p in paths]
    res = client.post("/api/runs/preview", files=files)
    assert res.status_code == 200, res.text
    return res.json()


def test_catalog_document_preview(client, db, spec):
    """Scenario: 문서 목록에 있는 문서 추천 — 문서 목록에 있는 문서 추천"""
    [p] = preview(client, spec)
    assert (p["bundle"], p["judge_target"], p["in_catalog"], p["file_no"]) == ("A", True, True, 91)
    assert p["reason"] == "문서 목록의 묶음 A"
    assert count(db, "document") == 0 and count(db, "review_run") == 0


def test_iec_document_not_in_catalog_preview(client, tmp_path):
    """Scenario: 문서 목록에 없는 IEC 문서 추천 — 문서 목록에 없는 IEC 문서 추천"""
    [p] = preview(client, build_judgment_spec(tmp_path / "new_iec_datasheet.docx", IEC_TITLE))
    assert (p["bundle"], p["judge_target"], p["in_catalog"]) == ("B", True, False)
    assert p["standard_system"] == "IEC" and "IEC 규격 문서" in p["reason"]


def test_not_judged_document_preview(client, tmp_path):
    """Scenario: 판정하지 않는 문서 추천 — 판정하지 않는 문서 추천"""
    [p] = preview(client, build_judgment_spec(tmp_path / "new_plain_datasheet.docx"))
    assert (p["bundle"], p["judge_target"], p["in_catalog"]) == ("C", False, False)
    assert "판정하지 않음" in p["reason"]


def test_library_preview_needs_existing_files(client):
    res = client.post("/api/runs/library/preview", json={"files": ["없는 파일.docx"]})
    assert res.status_code == 400


def test_bundle_c_document_set_to_b(db, tmp_path):
    """Scenario: 묶음 C 문서를 B로 정하고 시작 — 묶음 C 문서를 B로 정하고 시작"""
    path = build_judgment_spec(tmp_path / "new_plain_datasheet.docx")
    catalog = count(db, "document_catalog")
    run_id = run_once(db, [path], {path.name: {"bundle": "B"}})
    [doc] = queries.run_documents(db, run_id)
    assert (doc["bundle"], doc["judge_target"], doc["classify_by"], doc["needs_review"]) == \
        ("B", True, "HUMAN", False)
    assert count(db, "judgment") > 0
    assert count(db, "document_catalog") == catalog


def test_same_file_with_another_bundle(db, tmp_path):
    """Scenario: 같은 파일을 다른 묶음으로 다시 시작 — 같은 파일을 다른 묶음으로 다시 시작"""
    path = build_judgment_spec(tmp_path / "new_plain_datasheet.docx")
    first = run_once(db, [path])
    second = run_once(db, [path], {path.name: {"bundle": "B"}})
    [a] = queries.run_documents(db, first)
    [b] = queries.run_documents(db, second)
    assert a["document_id"] != b["document_id"]
    assert (a["bundle"], a["judge_target"], a["classify_by"]) == ("C", False, "RULE")
    assert (b["bundle"], b["judge_target"], b["classify_by"]) == ("B", True, "HUMAN")
    assert db.execute("SELECT count(*) FROM judgment WHERE run_id = %s",
                      (first,)).fetchone()[0] == 0
    # 규칙과 같은 값을 보내면 규칙 결과를 그대로 다시 쓴다
    third = run_once(db, [path], {path.name: {"bundle": "C"}})
    assert queries.run_documents(db, third)[0]["document_id"] == a["document_id"]


def test_upload_with_choices(client, db, tmp_path):
    path = build_judgment_spec(tmp_path / "new_plain_datasheet.docx")
    files = [("files", (path.name, path.read_bytes()))]
    choose = lambda bundle: {"choices": json.dumps({path.name: {"bundle": bundle}}),  # noqa: E731
                              "due_date": "2026-12-01"}
    bad = client.post("/api/runs", files=files, data=choose("E"))
    assert bad.status_code == 400
    res = client.post("/api/runs", files=files, data=choose("B"))
    assert res.status_code == 202
    [doc] = client.get(f"/api/runs/{res.json()['run_id']}/documents").json()
    assert (doc["bundle"], doc["classify_by"]) == ("B", "HUMAN")


def test_preview_rejects_broken_docx(client):
    res = client.post("/api/runs/preview", files=[("files", ("빈 파일.docx", b""))])
    assert res.status_code == 400 and "열 수 없습니다" in res.json()["detail"]


def test_same_file_uploaded_at_once(db, tmp_path, monkeypatch):
    """Scenario: 같은 파일을 거의 동시에 두 번 올림.

    늦게 넣은 쪽은 먼저 처리된 결과를 다시 쓴다.
    """
    from rfp_agent.pipeline import document
    path = build_judgment_spec(tmp_path / "new_plain_datasheet.docx")
    first = run_once(db, [path], {path.name: {"bundle": "B"}})
    real = document._find_existing
    calls = []

    def missed_once(*args):
        # 다른 검토가 아직 넣기 전에 찾아본 것처럼, 처음 한 번은 못 찾은 것으로 한다
        calls.append(1)
        return None if len(calls) == 1 else real(*args)

    monkeypatch.setattr(document, "_find_existing", missed_once)
    documents = count(db, "document")
    second = run_once(db, [path], {path.name: {"bundle": "B"}})
    assert len(calls) == 2                                   # 넣다가 겹쳐 다시 찾음
    assert count(db, "document") == documents                # 새 문서 행 없음
    assert queries.run_documents(db, second)[0]["document_id"] == \
        queries.run_documents(db, first)[0]["document_id"]
    assert db.execute("SELECT count(*) FROM judgment WHERE run_id = %s",
                      (second,)).fetchone()[0] > 0


def upload(client, paths, choices=None):
    files = [("files", (p.name, p.read_bytes())) for p in paths]
    data = ({"choices": json.dumps(choices)} if choices else {}) | {"due_date": "2026-12-01"}
    return client.post("/api/runs", files=files, data=data)


def test_reject_bundle_c_only(client, db, tmp_path):
    """Scenario: 묶음 C 문서만 올려 등록 — 거절되고 검토 실행이 생기지 않는다."""
    path = build_judgment_spec(tmp_path / "new_plain_datasheet.docx")
    res = upload(client, [path])
    assert res.status_code == 400 and "판정 대상 문서" in res.json()["detail"]
    assert count(db, "review_run") == 0 and count(db, "document") == 0
    # 사람이 C로 정해 보내도 같다
    assert upload(client, [path], {path.name: {"bundle": "C"}}).status_code == 400
    assert count(db, "review_run") == 0


def test_start_when_human_sets_bundle_b(client, db, tmp_path):
    """Scenario: 사람이 묶음 B로 정해 등록 — 검토가 시작된다."""
    path = build_judgment_spec(tmp_path / "new_plain_datasheet.docx")
    res = upload(client, [path], {path.name: {"bundle": "B"}})
    assert res.status_code == 202, res.text
    assert count(db, "review_run") == 1


def test_start_with_one_judge_target(client, db, spec, tmp_path):
    """Scenario: 판정 대상이 하나라도 있으면 시작 — 묶음 C 문서도 함께 저장된다."""
    other = build_judgment_spec(tmp_path / "new_plain_datasheet.docx")
    res = upload(client, [spec, other])
    assert res.status_code == 202, res.text
    docs = client.get(f"/api/runs/{res.json()['run_id']}/documents").json()
    assert sorted(d["bundle"] for d in docs) == ["A", "C"]


def test_broken_docx_is_not_rejected_here(client, db):
    """열 수 없는 docx는 거절 판단에서 빼고 지금처럼 분석 실패로 남긴다."""
    res = client.post("/api/runs", files=[("files", ("빈 파일.docx", b""))],
                      data={"due_date": "2026-12-01"})
    assert res.status_code == 202
