"""분석 밖 AI 사용량 기록 (change add-ai-usage-log).

명세 review-run "분석 밖 AI 사용량 기록"의 Scenario. API가 쓰는 AI를 사용량을 세는 가짜로 바꾼다.
"""

import pytest

from rfp_agent.llm.client import Usage
from rfp_agent.pipeline.run import RunContext, create_run, execute_run

VERSION = "test-dict-v1"


class CountingLLM:
    """검토 도우미 질문에 바로 "맞는 조항 없음"으로 답하고, 요청마다 토큰 100·10·5를 센다."""

    model = "gemini-3.8-flash"

    def __init__(self):
        self.usage = Usage()

    def generate_json(self, prompt, schema):
        # 호출 수는 부르는 쪽(call_with_retry)이 센다
        self.usage.add(input_tokens=100, output_tokens=10, thinking_tokens=5)
        return {"action": "answer", "sentences": []}


@pytest.fixture
def client(db, db_url, monkeypatch):
    from fastapi.testclient import TestClient

    from rfp_agent.api.main import app
    from rfp_agent.config import get_settings

    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    yield TestClient(app)
    get_settings.cache_clear()


@pytest.fixture
def run_id(db, spec):
    run_id = create_run(db, VERSION, None)
    assert execute_run(RunContext(db, VERSION, None, None), run_id, [spec]) == "ENGINEER_REVIEW"
    return run_id


def ai(monkeypatch, llm):
    monkeypatch.setattr("rfp_agent.pipeline.service.make_llm", lambda settings: llm)


def usage_rows(db):
    return db.execute("SELECT feature, run_id, model, calls, input_tokens FROM ai_usage "
                      "ORDER BY usage_id").fetchall()


def test_assistant_usage(db, client, run_id, monkeypatch):
    """Scenario: 검토 도우미 사용량 — 그 검토, 호출 수, 토큰이 남는다."""
    ai(monkeypatch, CountingLLM())
    assert client.post(f"/api/runs/{run_id}/assistant", json={"question": "gas leakage"}) \
        .status_code == 200
    [(feature, run, model, calls, tokens)] = usage_rows(db)
    assert (feature, run, model) == ("ASSISTANT", run_id, "gemini-3.8-flash")
    assert calls >= 1 and tokens == 100 * calls


def test_no_ai_no_usage(db, client, run_id, monkeypatch):
    """Scenario: AI를 부르지 않은 요청 — AI가 꺼져 있으면 남지 않는다."""
    ai(monkeypatch, None)
    assert client.post(f"/api/runs/{run_id}/assistant", json={"question": "gas leakage"}) \
        .status_code == 200
    assert usage_rows(db) == []


def test_usage_by_day_and_feature(db, client, run_id, monkeypatch):
    """Scenario: 날짜·기능별 사용량 — 검토 도우미 합과 분석 줄이 따로, 합계에 추정 비용."""
    ai(monkeypatch, CountingLLM())
    for question in ("gas leakage", "rated voltage"):
        client.post(f"/api/runs/{run_id}/assistant", json={"question": question})
    db.execute("UPDATE review_run SET llm_model = 'gemini-3.8-flash', llm_calls = 22, "
               "llm_input_tokens = 6400, llm_output_tokens = 2036, llm_thinking_tokens = 11144 "
               "WHERE run_id = %s", (run_id,))
    db.commit()
    body = client.get("/api/ai-usage?days=7").json()
    rows = {r["feature"]: r for r in body["items"]}
    asked = sum(c for (_, _, _, c, _) in usage_rows(db))
    assert (rows["ASSISTANT"]["calls"], rows["ASSISTANT"]["feature_name"]) == (asked, "검토 도우미")
    assert (rows["ANALYSIS"]["calls"], rows["ANALYSIS"]["estimated_cost_krw"]) == (22, 84)
    assert body["total_calls"] == asked + 22
    assert body["total_cost_krw"] == sum(r["estimated_cost_krw"] for r in body["items"])
