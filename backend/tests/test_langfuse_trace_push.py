"""검토 실행 작업이 끝날 때 AI 호출 기록을 Langfuse로 (change add-langfuse-trace-push).

명세 prompt-evaluation "Langfuse로 호출 기록 보내기"의 자동 전송 Scenario. 작업은 실행 대기열
(`run_queue.drain`)로 돌리고 AI는 대역(FakeLLM), Langfuse는 가짜 서버.
"""

import pytest
from fastapi.testclient import TestClient

from rfp_agent.api.main import app
from rfp_agent.config import get_settings
from rfp_agent.pipeline import ai_calls, run_queue, service
from rfp_agent.pipeline.run import create_run
from tests.conftest import FakeLLM
from tests.test_langfuse_experiments import HOST, FakeLangfuseData
from tests.test_langfuse_prompts import fake_langfuse

VERSION = "test-dict-v1"


@pytest.fixture
def langfuse(db, db_url, monkeypatch):
    fake = FakeLangfuseData()
    monkeypatch.setattr("tests.test_langfuse_prompts.FakeLangfuse", lambda: fake)
    monkeypatch.setenv("RFP_LANGFUSE_RECORD", "on")
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setattr(service, "make_llm", lambda settings: FakeLLM())
    yield from fake_langfuse(monkeypatch)
    get_settings.cache_clear()


def _run(db, spec) -> int:
    run_id = create_run(db, VERSION, None)
    run_queue.enqueue(db, run_id, "START", [spec], {spec.name: {"bundle": "B"}})
    db.commit()
    assert run_queue.drain(1) == 1
    db.commit()
    assert db.execute("SELECT stage FROM review_run WHERE run_id = %s",
                      (run_id,)).fetchone()[0] == "ENGINEER_REVIEW"
    return run_id


def _calls(run_id: int) -> dict:
    return TestClient(app).get(f"/api/runs/{run_id}/ai-calls").json()


def test_sent_when_job_ends(db, spec, langfuse):
    """Scenario: 분석이 끝나면 호출 기록을 저절로 보냄 — 내려받기와 같은 내용 한 번, 시각·링크."""
    run_id = _run(db, spec)
    assert len(langfuse.traces) == 1
    assert langfuse.traces[0] == ai_calls.otel(db, run_id)
    token = db.execute("SELECT run_token::text FROM ai_call WHERE run_id = %s LIMIT 1",
                       (run_id,)).fetchone()[0]
    info = _calls(run_id)["langfuse"]
    trace_id = ai_calls._hex(f"run-{run_id}-{token}", 32)
    assert info["sent_at"] and info["error"] is None
    assert info["url"] == f"{HOST}/project/proj1/traces/{trace_id}"


def test_unreachable_keeps_review(db, spec, langfuse):
    """Scenario: 호출 기록을 보내지 못해도 검토는 그대로 — 담당자 확인, 보내지 못한 이유."""
    langfuse.down = True
    run_id = _run(db, spec)                                    # 검토 단계는 그대로
    info = _calls(run_id)["langfuse"]
    assert info["sent_at"] is None and info["url"] is None
    assert info["error"].startswith("Langfuse 요청 실패")
    # 다시 닿으면 다음 작업 끝에 보내고 이유를 지운다
    langfuse.down = False
    from rfp_agent.pipeline import langfuse_ops

    assert langfuse_ops.send_run(db, run_id, None) == "SENT"
    info = _calls(run_id)["langfuse"]
    assert info["sent_at"] and info["error"] is None


def test_off_sends_nothing(db, spec, langfuse, monkeypatch):
    """Scenario: 끄면 저절로 보내지 않음 — 요청 없음, 실행 기록 상세에 Langfuse 줄 없음."""
    monkeypatch.setenv("RFP_LANGFUSE_RECORD", "off")
    monkeypatch.setenv("RFP_LANGFUSE", "off")
    get_settings.cache_clear()
    run_id = _run(db, spec)
    assert langfuse.requests == []
    body = _calls(run_id)
    assert body["count"] > 0 and body["langfuse"] is None


def test_no_ai_calls_sends_nothing(db, spec, langfuse, monkeypatch):
    """AI를 끈 검토처럼 호출이 없으면 보내지 않고 남기지 않는다."""
    monkeypatch.setattr(service, "make_llm", lambda settings: None)
    run_id = _run(db, spec)
    assert langfuse.traces == [] and _calls(run_id)["langfuse"] is None
