"""검토에 문서 더하기 (change add-document-addendum).

명세 review-run "검토에 문서 추가"·review-approval "문서 추가 뒤 확인 이어받기"의 Scenario.
"""

import pytest

from rfp_agent.pipeline import doc_add, queries, review
from rfp_agent.pipeline.review import ReviewError
from rfp_agent.pipeline.run import RunContext, create_run, execute_run
from tests.docx_factory import build_gis_spec

VERSION = "test-dict-v1"


def ctx(conn):
    return RunContext(conn, VERSION, None, None)


def engineer(conn):
    return conn.execute("SELECT min(user_id) FROM app_user WHERE role = 'ENGINEER'").fetchone()[0]


def finished(conn, spec):
    run_id = create_run(conn, VERSION, None)
    assert execute_run(ctx(conn), run_id, [spec]) == "ENGINEER_REVIEW"
    return run_id


def current(conn, run_id):
    return {r[0]: r[1:] for r in conn.execute(
        """SELECT (requirement_id, value_id, product_code, compare_rule_id)::text,
                  judgment_id, review_status, result
           FROM judgment WHERE run_id = %s AND is_current""", (run_id,))}


def add(conn, run_id, extra, choices=None):
    paths, merged = doc_add.prepare_add(conn, run_id, [extra],
                                        choices or {extra.name: {"bundle": "A"}}, engineer(conn))
    assert execute_run(ctx(conn), run_id, paths, merged) == "ENGINEER_REVIEW"
    return paths


def test_add_document_keeps_confirmed(db, spec, tmp_path):
    """Scenario: 확정한 판정은 그대로 — 추가 문서의 줄은 후보, 이력에 "문서 추가" 1건."""
    run_id = finished(db, spec)
    first = current(db, run_id)
    key, (jid, _, _) = next(iter(sorted(first.items())))
    review.act(ctx(db), run_id, "judgment", jid, "CONFIRM", actor_id=engineer(db))
    docs_before = len(queries.run_documents(db, run_id))
    paths = add(db, run_id, build_gis_spec(tmp_path / "addendum_gis.docx"))
    assert [p.name for p in paths] == [spec.name, "addendum_gis.docx"]
    after = current(db, run_id)
    assert len(queries.run_documents(db, run_id)) == docs_before + 1
    assert after[key][1] == "CONFIRMED" and after[key][0] != jid
    new_keys = set(after) - set(first)
    assert new_keys and all(after[k][1] == "CANDIDATE" for k in new_keys)
    [entry] = db.execute("SELECT after_value FROM review_log WHERE run_id = %s "
                         "AND target_table = 'run_document' AND action = 'ADD'",
                         (run_id,)).fetchall()
    assert entry[0] == {"files": ["addendum_gis.docx"]}


def test_add_document_keeps_edit_and_reject(db, spec, tmp_path):
    """Scenario: 수정·반려도 이어받음 — 수정한 판정 값과 반려 상태가 새 줄에 남는다."""
    run_id = finished(db, spec)
    rows = sorted(current(db, run_id).items())
    (k1, (j1, _, r1)), (k2, (j2, _, _)) = rows[0], rows[1]
    new_result = "QUERY_CANDIDATE" if r1 != "QUERY_CANDIDATE" else "COMPLY"
    review.act(ctx(db), run_id, "judgment", j1, "EDIT", {"result": new_result}, "고객 확인",
               engineer(db))
    review.act(ctx(db), run_id, "judgment", j2, "REJECT", None, "해당 없음", engineer(db))
    add(db, run_id, build_gis_spec(tmp_path / "addendum_gis.docx"))
    after = current(db, run_id)
    assert after[k1][1:] == ("EDITED", new_result)
    assert after[k2][1] == "REJECTED"


def test_add_document_keeps_risk_status(db, spec, tmp_path):
    """Scenario: 위험 조건 확인도 이어받음 — 같은 표현·요구사항의 위험 조건은 확인 상태 그대로."""
    gis = build_gis_spec(tmp_path / "synthetic_154kV_GIS_spec.docx")
    run_id = create_run(db, VERSION, None)
    assert execute_run(ctx(db), run_id, [gis], {gis.name: {"bundle": "A"}}) == "ENGINEER_REVIEW"
    risk_id = db.execute("SELECT min(risk_id) FROM risk_flag WHERE run_id = %s",
                         (run_id,)).fetchone()[0]
    assert risk_id
    before = doc_add.risk_statuses(db, run_id)
    assert before == {}
    review.act(ctx(db), run_id, "risk_flag", risk_id, "CONFIRM", actor_id=engineer(db))
    seen = doc_add.risk_statuses(db, run_id)
    add(db, run_id, spec, {spec.name: {"bundle": "B"}})
    assert doc_add.risk_statuses(db, run_id) == seen
    n = db.execute("SELECT count(*) FROM risk_flag WHERE run_id = %s AND status = 'CONFIRMED'",
                   (run_id,)).fetchone()[0]
    assert n == 1


def test_add_document_only_in_engineer_review(db, spec, tmp_path):
    """Scenario: 상신한 검토에는 못 더함 — 담당자 확인 단계가 아니면 409, 검토는 그대로."""
    run_id = finished(db, spec)
    db.execute("UPDATE review_run SET stage = 'APPROVAL' WHERE run_id = %s", (run_id,))
    db.commit()
    with pytest.raises(ReviewError) as err:
        doc_add.prepare_add(db, run_id, [build_gis_spec(tmp_path / "a.docx")], {}, engineer(db))
    assert err.value.status == 409 and "결재 상신 전" in str(err.value)
    assert queries.run_summary(db, run_id)["stage"] == "APPROVAL"


def test_add_same_file_rejected(db, spec):
    """Scenario: 같은 파일 다시 더하기 — 이미 있는 파일 이름이면 409."""
    run_id = finished(db, spec)
    with pytest.raises(ReviewError) as err:
        doc_add.prepare_add(db, run_id, [spec], {}, engineer(db))
    assert err.value.status == 409 and spec.name in str(err.value)
    assert queries.run_summary(db, run_id)["stage"] == "ENGINEER_REVIEW"


def test_add_document_keeps_warranty(db, spec, tmp_path):
    """Scenario: 확정한 보증값 그대로 —
    확정한 보증값 후보는 새 판정 줄에 다시 이어져 그대로 남는다."""
    run_id = finished(db, spec)
    row = db.execute("""SELECT w.candidate_id, w.judgment_id FROM warranty_candidate w
                        WHERE w.run_id = %s AND w.candidate_value IS NOT NULL
                        ORDER BY 1 LIMIT 1""", (run_id,)).fetchone()
    if row is None:
        pytest.skip("합성 문서에 값이 있는 보증값 후보가 없음")
    review.act(ctx(db), run_id, "warranty_candidate", row[0], "CONFIRM", actor_id=engineer(db))
    add(db, run_id, build_gis_spec(tmp_path / "addendum_gis.docx"))
    rows = db.execute("""SELECT w.status, j.is_current FROM warranty_candidate w
                         JOIN judgment j USING (judgment_id)
                         WHERE w.run_id = %s AND w.status = 'CONFIRMED'""", (run_id,)).fetchall()
    assert rows == [("CONFIRMED", True)]



def explain_calls(llm):
    return sum("왜 위험한지" in p for p in llm.prompts)


def test_add_document_reuses_risk_explanation(db, spec, tmp_path):
    """Scenario: 같은 위험 조건은 AI 다시 안 부름 —
    같은 위험 조건은 AI에 다시 묻지 않고 설명과 근거 문장을 이어 쓴다 (문서 추가 비용)."""
    from tests.conftest import FakeLLM

    gis = build_gis_spec(tmp_path / "synthetic_154kV_GIS_spec.docx")
    llm = FakeLLM()
    run_id = create_run(db, VERSION, llm)
    run_ctx = RunContext(db, VERSION, llm, None)
    assert execute_run(run_ctx, run_id, [gis], {gis.name: {"bundle": "A"}}) == "ENGINEER_REVIEW"
    old_keys = {key for key, _ in doc_add.risk_snapshot(db, run_id).values()}
    first = explain_calls(llm)
    assert first and old_keys
    paths, merged = doc_add.prepare_add(db, run_id, [spec], {spec.name: {"bundle": "B"}},
                                        engineer(db))
    assert execute_run(run_ctx, run_id, paths, merged) == "ENGINEER_REVIEW"
    now = doc_add.risk_snapshot(db, run_id)
    added = [k for k, _ in now.values() if k not in old_keys]
    assert explain_calls(llm) - first == len(added)        # 새 위험 조건만 AI에 묻는다
    orphan = db.execute(
        """SELECT count(*) FROM claim_evidence c WHERE run_id = %s AND target_table = 'risk_flag'
           AND NOT EXISTS (SELECT 1 FROM risk_flag f WHERE f.risk_id = c.target_id)""",
        (run_id,)).fetchone()[0]
    kept = db.execute(
        """SELECT count(DISTINCT target_id) FROM claim_evidence WHERE run_id = %s
           AND target_table = 'risk_flag' AND target_id = ANY(%s)""",
        (run_id, list(now))).fetchone()[0]
    assert orphan == 0 and kept >= len(old_keys & {k for k, _ in now.values()})


def test_add_documents_api(db, db_url, monkeypatch, spec, tmp_path):
    """Scenario: 문서를 더해 다시 분석 / 엔지니어만 더함 —
    문서 추가 API: 엔지니어만(승인자 403), 끝나면 담당자 확인 단계, 문서 하나 늘어남."""
    import json

    from fastapi.testclient import TestClient

    from rfp_agent.api.main import app
    from rfp_agent.config import get_settings

    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    get_settings.cache_clear()
    try:
        client = TestClient(app)
        files = [("files", (spec.name, spec.read_bytes()))]
        run_id = client.post("/api/runs", files=files,
                             data={"due_date": "2026-12-01"}).json()["run_id"]
        extra = build_gis_spec(tmp_path / "addendum_gis.docx")
        files = [("files", (extra.name, extra.read_bytes()))]
        data = {"choices": json.dumps({extra.name: {"bundle": "A"}})}
        approver = db.execute("SELECT min(user_id) FROM app_user WHERE role = 'APPROVER'"
                              ).fetchone()[0]
        res = client.post(f"/api/runs/{run_id}/documents", files=files,
                          data={**data, "actor_id": str(approver)})
        assert res.status_code == 403
        res = client.post(f"/api/runs/{run_id}/documents", files=files,
                          data={**data, "actor_id": str(engineer(db))})
        assert res.status_code == 202, res.text
        assert client.get(f"/api/runs/{run_id}").json()["stage"] == "ENGINEER_REVIEW"
        docs = client.get(f"/api/runs/{run_id}/documents").json()
        assert len(docs) == 2 and "addendum_gis.docx" in [d["file_name"] for d in docs]
        again = client.post(f"/api/runs/{run_id}/documents", files=files, data=data)
        assert again.status_code == 409
    finally:
        get_settings.cache_clear()
