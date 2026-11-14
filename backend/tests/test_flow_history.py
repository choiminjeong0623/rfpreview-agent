"""흐름 기록 보기 (change add-flow-history, C2).

명세 review-run "흐름 기록 응답"의 Scenario. 화면은 frontend/e2e/flow-history.spec.ts.
"""

import pytest
from fastapi.testclient import TestClient

from rfp_agent.api.main import app
from rfp_agent.pipeline import graph_flow, queries, review
from rfp_agent.pipeline.run import RunContext, create_run, execute_run

VERSION = "test-dict-v1"
PROCESS = ["documents", "pairs", "risks", "judge", "meaning", "check", "warranty", "loss",
           "outputs", "proposals", "assign"]


@pytest.fixture
def run(db, spec):
    run_id = create_run(db, VERSION, None)
    assert execute_run(RunContext(db, VERSION, None, None), run_id, [spec]) == "ENGINEER_REVIEW"
    return run_id


def test_flow_until_engineer_review(db, run):
    """Scenario: 담당자 확인까지 처리한 검토 — 단계 순서, 판정 수 0 → n, 멈춘 자리, 단계 그대로."""
    flow = graph_flow.history(db, run)
    assert flow["recorded"] is True and flow["stop"] == "engineer_review"
    assert [s["node"] for s in flow["steps"]] == PROCESS
    judge = next(s for s in flow["steps"] if s["node"] == "judge")
    judgments = queries.run_summary(db, run)["judgments"]
    assert {"key": "judgment_count", "before": None, "after": judgments} in judge["changes"]
    assert all(s["seconds"] >= 0 and s["action"] is None for s in flow["steps"])
    assert graph_flow.history(db, run) == flow                    # 다시 불러도 같음 (읽기만)
    assert queries.run_summary(db, run)["stage"] == "ENGINEER_REVIEW"


def test_flow_after_submit(db, run):
    """Scenario: 상신한 검토 — 담당자 확인 단계에 사람 동작 "상신", 멈춘 자리는 승인 대기."""
    review.finish_review(db, run, review.default_user(db, "APPROVER"), "상신합니다",
                         review.default_user(db, "ENGINEER"))
    flow = graph_flow.history(db, run)
    last = flow["steps"][-1]
    assert (last["node"], last["action"]) == ("engineer_review", "submit")
    assert flow["stop"] == "approval"


def test_flow_without_record(db):
    """Scenario: 흐름 기록이 없는 검토 — 빈 목록, 기록 없음."""
    run_id = create_run(db, VERSION, None)
    assert graph_flow.history(db, run_id) == {
        "run_id": run_id, "recorded": False, "stop": None, "next_node": None, "steps": []}


def test_flow_api(db, run, monkeypatch):
    """흐름 기록 API: 응답 스키마대로, 없는 검토는 404."""
    from contextlib import contextmanager

    import rfp_agent.api.runs as runs_api

    @contextmanager
    def same():
        yield db
    monkeypatch.setattr(runs_api, "connect", same)
    client = TestClient(app)
    body = client.get(f"/api/runs/{run}/flow").json()
    assert body["stop"] == "engineer_review" and body["steps"][0]["node"] == "documents"
    assert client.get("/api/runs/999999/flow").status_code == 404
