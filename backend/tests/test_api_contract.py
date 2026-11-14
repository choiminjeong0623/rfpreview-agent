"""API 응답 스키마 (명세 api-contract의 Scenario, change update-api-contract).

합성 문서 실행으로 모든 JSON API를 불러 응답이 공개한 모양(응답 모델)을 통과하는지 본다.
응답 모델은 모르는 칸을 받지 않으므로(extra="forbid"), 조회가 보낸 칸이 모델에 없어도 실패한다.
"""

import json
import logging
from pathlib import Path

import pytest

from rfp_agent.pipeline import queries, review
from rfp_agent.pipeline.loss import recalculate
from rfp_agent.pipeline.run import RunContext, create_run, execute_run
from tests.conftest import FakeLLM
from tests.docx_factory import build_gis_spec, build_loss_spec
from tests.test_engineering_check import build_check_spec

VERSION = "test-dict-v1"
OPENAPI_FILE = Path(__file__).parents[2] / "frontend" / "openapi.json"


@pytest.fixture
def client(db, db_url, monkeypatch):
    from fastapi.testclient import TestClient

    from rfp_agent.api.main import app
    from rfp_agent.config import get_settings

    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    get_settings.cache_clear()
    # 모양이 틀린 응답은 서버 오류(500)로 받아 실패 이유를 본다
    yield TestClient(app, raise_server_exceptions=False)
    get_settings.cache_clear()


def run_once(db, paths):
    llm = FakeLLM()
    # 같은 파일 번호(91)의 다른 합성 문서를 한 DB에서 돌리므로 처리 키가 겹치지 않게 한다
    llm.model = f"fake-model-{Path(paths[-1]).stem}"
    run_id = create_run(db, VERSION, llm)
    stage = execute_run(RunContext(db, VERSION, llm, None), run_id, paths)
    assert stage == "ENGINEER_REVIEW", db.execute(
        "SELECT failed_step, error_message FROM review_run WHERE run_id = %s", (run_id,)).fetchone()
    return run_id


@pytest.fixture
def run(db, spec):
    """판정·보증값·일탈·질의·제안 포인트가 있는 실행."""
    return run_once(db, [spec])


@pytest.fixture
def run_more(db, tmp_path):
    """위험 조건·손실 환산이 있는 실행."""
    return run_once(db, [build_gis_spec(tmp_path / "synthetic_154kV_bundle_a.docx"),
                         build_loss_spec(tmp_path / "synthetic_judgment_loss.docx")])


@pytest.fixture
def run_check(db, tmp_path):
    """공학 검산이 있는 실행 (같은 파일 번호라 따로 돌린다)."""
    return run_once(db, [build_check_spec(tmp_path / "synthetic_judgment_check.docx")])


def ok(res):
    assert res.status_code == 200, f"{res.request.url}: {res.status_code} {res.text[:500]}"
    return res.json()


def run_paths(run_id: int, user_id: int) -> list[str]:
    base = f"/api/runs/{run_id}"
    return [base] + [f"{base}/{p}" for p in (
        "documents", "pairs", "requirements", "risks", "judgments", "judgment-counts",
        "equipment", "warranty", "losses", "outputs", "tbe", "tbe?lang=both&include=confirmed",
        "datasheets", "submission-check", "checks", "proposals", "history", "approval",
        "read-checks", "deliverables", "assignments?role=COST")] + [
        f"/api/tasks?user_id={user_id}"]


def test_every_api_passes_its_model(db, run, run_more, run_check, client):
    """모든 JSON 조회 API와 쓰기 API가 응답 모델을 통과한다."""
    engineer = review.default_user(db, "ENGINEER")
    for path in ["/api/health", "/api/users", "/api/runs", "/api/library",
                 "/api/assignments?role=QUALITY", "/api/products", "/api/products/families",
                 "/api/rules/compare", "/api/rules/items", "/api/rules/risk-expressions",
                 *run_paths(run, engineer), *run_paths(run_more, engineer),
                 *run_paths(run_check, engineer)]:
        ok(client.get(path))
    # 빈 목록만 보고 지나가지 않도록, 근거 응답마다 줄이 하나 이상 있는지 본다
    for run_id, kinds in ((run, ["judgments", "warranty", "outputs", "proposals"]),
                          (run_more, ["risks", "losses"]), (run_check, ["checks"])):
        for kind in kinds:
            assert ok(client.get(f"/api/runs/{run_id}/{kind}")), kind

    base = f"/api/runs/{run}"
    judgments = ok(client.get(f"{base}/judgments"))
    ok(client.get(f"/api/requirements/{judgments[0]['requirement_id']}?run_id={run}"))
    ok(client.get(f"/api/products/{judgments[0]['product_code']}"))
    for sheet in ok(client.get(f"{base}/datasheets")):
        ok(client.get(f"{base}/datasheet", params={"table_id": sheet["table_id"]}))

    # 쓰기 API
    ok(client.post(f"{base}/actions", json={"target": "judgment",
                                             "target_id": judgments[0]["judgment_id"],
                                             "action": "CONFIRM", "actor_id": engineer}))
    ok(client.post(f"{base}/actions/bulk",
                   json={"ids": [j["judgment_id"] for j in judgments[1:3]], "actor_id": engineer}))
    ok(client.put(f"{base}/info", json={"review_name": "예시 검토", "actor_id": engineer}))
    ok(client.post(f"{base}/submission-check"))
    group = judgments[0]["equipment_group"]
    ok(client.put(f"{base}/equipment/{group}/product", json={"product_code": None}))
    for check in ok(client.get(f"{base}/read-checks"))[:1]:
        ok(client.post(f"{base}/read-checks/{check['key']}", json={"actor_id": engineer}))
        ok(client.delete(f"{base}/read-checks/{check['key']}"))
    for task in ok(client.get(f"/api/runs/{run}/assignments?role=QUALITY"))[:1]:
        ok(client.post(f"{base}/assignments/send",
                       json={"assignment_ids": [task["assignment_id"]], "actor_id": engineer}))
        ok(client.put(f"/api/assignments/{task['assignment_id']}",
                      json={"status": "DONE", "actor_id": engineer, "reply_note": "받음"}))
    approver = review.default_user(db, "APPROVER")
    submit = {"approver_id": approver, "comment": "질의 회신 예정", "actor_id": engineer}
    ok(client.post(f"{base}/finish-review", json=submit))
    ok(client.post(f"{base}/withdraw", json={"actor_id": engineer}))
    ok(client.post(f"{base}/finish-review", json=submit))
    ok(client.post(f"{base}/approval", json={"decision": "REJECTED", "comment": "다시 확인",
                                              "actor_id": approver}))
    ok(client.post(f"{base}/reopen", json={"actor_id": engineer}))
    for path in [*run_paths(run, engineer), f"/api/tasks?user_id={approver}"]:
        ok(client.get(path))

    loss = ok(client.get(f"/api/runs/{run_more}/losses"))[0]
    ok(client.put(f"/api/runs/{run_more}/losses/{loss['loss_calc_id']}",
                  json={"loss_noload_kw": 60, "loss_load_kw": 300, "loss_aux_kw": 8}))


def test_judgment_list_schema(client):
    """Scenario: 판정 목록의 응답 모양."""
    spec = ok(client.get("/openapi.json"))
    body = spec["paths"]["/api/runs/{run_id}/judgments"]["get"]["responses"]["200"]
    items = body["content"]["application/json"]["schema"]["items"]
    assert items == {"$ref": "#/components/schemas/Judgment"}
    judgment = spec["components"]["schemas"]["Judgment"]
    for field in ("judgment_id", "requirement_id", "result", "is_assumed", "locations"):
        assert field in judgment["required"]
    assert judgment["properties"]["result"]["enum"] == [
        "COMPLY", "DEVIATION_CANDIDATE", "QUERY_CANDIDATE", "NEEDS_REVIEW", "WARRANTY_TO_FILL"]
    assert judgment["properties"]["margin_value"]["anyOf"] == [{"type": "number"},
                                                              {"type": "null"}]
    assert judgment["properties"]["locations"]["minItems"] == 1
    location = spec["components"]["schemas"]["Location"]
    assert "file_no" in location["required"]
    assert location["properties"]["file_no"]["type"] == "integer"


def test_file_download_schema(client):
    """Scenario: 파일 내려받기 API."""
    spec = ok(client.get("/openapi.json"))
    for path, media in (("/api/runs/{run_id}/tbe/export", "spreadsheetml.sheet"),
                        ("/api/runs/{run_id}/datasheet/export", "spreadsheetml.sheet"),
                        ("/api/runs/{run_id}/outputs/export", "wordprocessingml.document")):
        content = spec["paths"][path]["get"]["responses"]["200"]["content"]
        assert list(content) == [f"application/vnd.openxmlformats-officedocument.{media}"]


def test_unknown_judgment_result(db, run, client, monkeypatch, caplog):
    """Scenario: 정해진 값 밖의 판정 결과 — 보내지 않고 서버 오류, 원인을 기록한다."""
    rows = queries.run_judgments(db, run)
    rows[0]["result"] = "MAYBE"
    monkeypatch.setattr(queries, "run_judgments", lambda *a, **k: rows)
    with caplog.at_level(logging.ERROR, logger="rfp_agent.api.main"):
        res = client.get(f"/api/runs/{run}/judgments")
    assert res.status_code == 500
    assert "MAYBE" not in res.text and "Rated" not in res.text
    assert f"/api/runs/{run}/judgments" in caplog.text and "0.result" in caplog.text
    assert "MAYBE" not in caplog.text          # 값(원문 문장 등)은 로그에 남기지 않는다


def test_empty_value_stays_empty(db, run, client):
    """Scenario: 비어 있는 값 — 제품 값이 없으면 null 그대로, 0으로 채우지 않는다."""
    judgments = ok(client.get(f"/api/runs/{run}/judgments", params={"limit": 500}))
    empty = [j for j in judgments if j["reason_code"] == "NO_PRODUCT_VALUE"]
    assert empty
    for j in empty:
        assert j["product_value_raw"] is None and j["margin_value"] is None


def test_judgment_without_location(db, run, client, monkeypatch):
    """Scenario: 위치가 없는 판정 — 목록에 없고, 모든 줄에 파일 번호가 있는 위치가 있다."""
    before = ok(client.get(f"/api/runs/{run}/judgments", params={"limit": 500}))
    gone = before[0]
    db.execute("DELETE FROM requirement_location WHERE requirement_id = %s",
               (gone["requirement_id"],))
    db.commit()
    after = ok(client.get(f"/api/runs/{run}/judgments", params={"limit": 500}))
    assert gone["judgment_id"] not in {j["judgment_id"] for j in after}
    assert len(after) < len(before)
    assert all(j["locations"] and all(loc["file_no"] for loc in j["locations"]) for j in after)

    # 조회가 위치 없는 줄을 거르지 못해도 응답 모델이 막는다
    rows = queries.run_judgments(db, run)
    rows[0]["locations"] = []
    monkeypatch.setattr(queries, "run_judgments", lambda *a, **k: rows)
    assert client.get(f"/api/runs/{run}/judgments").status_code == 500


def test_assumed_loss(db, run_more, client):
    """Scenario: 팀 가정 표시가 함께 감 — 사람이 넣은 손실값으로 계산하면 가정 여부가 참."""
    [loss] = ok(client.get(f"/api/runs/{run_more}/losses"))
    recalculate(db, loss["loss_calc_id"], 60, 300, 8)
    db.commit()
    [loss] = ok(client.get(f"/api/runs/{run_more}/losses"))
    assert loss["is_assumed"] is True and loss["total_usd"] == 1_240_400


def test_openapi_file_is_current():
    """Scenario: 서버 칸을 바꾸고 타입을 다시 만들지 않음 (서버 쪽).

    저장소의 frontend/openapi.json이 지금 응답 모델과 다르면 실패하고 다시 만드는 법을 알려 준다.
    화면 타입(src/api.gen.ts)은 frontend 검사(`npm run check:api`)가 이 파일로 다시 만들어 본다.
    """
    from rfp_agent.api.main import app

    current = json.loads(OPENAPI_FILE.read_text(encoding="utf-8"))
    assert current == app.openapi(), (
        f"{OPENAPI_FILE.name}이(가) 응답 모델과 다릅니다. "
        "`cd frontend && npm run gen:api`로 다시 만들어 커밋하세요.")
