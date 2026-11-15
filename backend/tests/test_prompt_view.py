"""프롬프트 관리 조회 (change add-prompt-view).

명세 prompt-evaluation "프롬프트 관리 화면 조회"의 Scenario.
"""

import pytest
from fastapi.testclient import TestClient

from rfp_agent.api.main import app
from rfp_agent.config import get_settings
from rfp_agent.llm import tasks
from rfp_agent.pipeline import prompt_eval as pe
from rfp_agent.pipeline import prompt_registry
from tests.conftest import FakeLLM
from tests.test_prompt_eval import Scripted, answers_for, jsonl, type_item
from tests.test_prompt_versions import run


def role_of(body: dict, role: str) -> dict:
    return next(r for r in body["roles"] if r["role"] == role)


def test_prompt_versions_with_history(db, db_url, spec, monkeypatch):
    """Scenario: 역할별 판과 판 기록 — 지금 판, 판마다 쓴 검토 수, 평가 점수가 보인다."""
    old_type = tasks.PROMPTS["type"]
    run(db, FakeLLM(), [spec])
    s = pe.parse_set("view", jsonl([type_item(n) for n in range(4)]))
    pe.save(db, pe.evaluate(s, Scripted(answers_for(s, wrong={"t000"})), "GEMINI"))
    monkeypatch.setitem(tasks.PROMPTS, "type", "t99")          # 판을 올린 뒤 한 번 더
    run(db, FakeLLM(), [spec])

    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    try:
        body = TestClient(app).get("/api/prompts").json()
    finally:
        get_settings.cache_clear()

    assert [r["role"] for r in body["roles"]] == list(tasks.PROMPTS)
    t = role_of(body, "type")
    assert t["label"] == "유형" and t["current"] == "t99" and t["in_doc_key"] and t["evaluated"]
    old, new = t["versions"]                                    # 처음 쓴 순서
    assert (old["version"], old["current"], old["runs"]) == (old_type, False, 1)
    assert (new["version"], new["current"], new["runs"]) == ("t99", True, 1)
    assert old["eval"]["metric"] == "유형 정확도" and old["eval"]["min"] == pytest.approx(75.0)
    assert new["eval"] is None                                  # 새 판은 아직 평가 안 함
    assert body["doc_key"].endswith(".t99")
    # 판을 바꾸지 않은 역할은 판 하나에 두 실행
    risk = role_of(body, "risk")
    assert [(v["version"], v["runs"]) for v in risk["versions"]] == [(tasks.PROMPTS["risk"], 2)]


def test_unused_role_shows_current_only(db):
    """Scenario: 아직 쓴 적 없는 판 — 지금 판 한 줄, 쓴 검토 0, 평가 없음."""
    body = prompt_registry.overview(db)
    h = role_of(body, "handoff")
    assert h["evaluated"] is False and h["in_doc_key"] is False
    assert h["versions"] == [{"version": tasks.PROMPTS["handoff"], "current": True, "runs": 0,
                              "first_used": None, "last_used": None, "calls": 0, "eval": None}]
