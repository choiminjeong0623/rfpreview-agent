"""프롬프트 관리 화면에서 고치기 (change add-prompt-editor).

명세 prompt-evaluation "화면에서 프롬프트 고쳐 staging에 저장", "화면에서 staging 판 평가",
"화면에서 운영으로 올리기"의 Scenario. Langfuse는 가짜 서버(test_langfuse_prompts.FakeLangfuse).
"""

import json

import pytest
from fastapi.testclient import TestClient

from rfp_agent.api.main import app
from rfp_agent.config import get_settings
from rfp_agent.llm import client as llm_client
from rfp_agent.llm import tasks
from rfp_agent.pipeline import prompt_editor
from rfp_agent.pipeline import prompt_eval as pe
from tests.conftest import as_user
from tests.test_langfuse_prompts import EDITED, fake_langfuse
from tests.test_prompt_eval import Scripted, answers_for


def user(db, role: str) -> int:
    return db.execute("SELECT min(user_id) FROM app_user WHERE role = %s", (role,)).fetchone()[0]


@pytest.fixture
def langfuse(monkeypatch):
    yield from fake_langfuse(monkeypatch)


@pytest.fixture
def client(db_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    prompt_editor._jobs.clear()
    yield TestClient(app)
    prompt_editor._jobs.clear()


def test_locked_without_langfuse(db, client):
    """Scenario: Langfuse가 없으면 고치기 잠김 — 코드 틀만 보이고 저장은 거절."""
    body = client.get("/api/prompts/type").json()
    assert body["connected"] is False and body["editable_reason"] == prompt_editor.NOT_CONNECTED
    assert body["code_template"] == tasks.TEMPLATES["type"] and "document" in body["slots"]
    r = client.post("/api/prompts/type/drafts",
                    headers=as_user(user(db, "ENGINEER")), json={"text": EDITED})
    assert r.status_code == 409


def test_save_draft_to_staging(db, client, langfuse):
    """Scenario: 고친 글을 staging에 저장 — 운영 판은 그대로, 검사에 걸리면 저장하지 않음."""
    prod = langfuse.add("type", tasks.TEMPLATES["type"], ["production"])
    eng = user(db, "ENGINEER")
    r = client.post("/api/prompts/type/drafts",
                    headers=as_user(eng), json={"text": EDITED, "message": "한 개만 고르게"})
    assert r.status_code == 200, r.text
    new = r.json()["version"]
    body = client.get("/api/prompts/type").json()
    assert body["connected"] and body["staging"]["version"] == new and body["staging"]["usable"]
    assert body["staging"]["commit_message"] == "한 개만 고르게"
    assert body["production"]["version"] == prod
    # 데이터 규칙을 지운 글, 자리표시자를 지운 글은 올리지 않음
    for bad, word in ((EDITED.replace(tasks.DATA_RULE, ""), "규칙"),
                      (EDITED.replace("{{document}}", ""), "{{doc_hint}}, {{document}}")):
        r = client.post("/api/prompts/type/drafts", headers=as_user(eng), json={"text": bad})
        assert r.status_code == 400 and word in r.json()["detail"]
    assert len(langfuse.prompts["rfp-type"]) == 2
    # 같은 글은 다시 올리지 않음, 협조 부서 사용자는 못 고침
    assert client.post("/api/prompts/type/drafts",
                       headers=as_user(eng), json={"text": EDITED}).status_code == 400
    assert client.post("/api/prompts/type/drafts", headers=as_user(user(db, "COST")),
                       json={"text": EDITED + " "}).status_code == 403


def _scripted(monkeypatch, wrong: set[str] = frozenset()):
    public = pe.load_set(pe.find_set("public", get_settings()))
    llm = Scripted(answers_for(public, wrong=wrong))
    monkeypatch.setattr(llm_client, "make_llm", lambda settings: llm)
    monkeypatch.setattr(llm_client, "ai_mode", lambda settings: "GEMINI")
    return public, llm


def test_eval_then_promote(db, client, langfuse, monkeypatch):
    """Scenario: 화면에서 staging 판 평가 후 운영으로 올리기.

    유형 문항만 staging 판으로 3번 평가하고, 기준선보다 나빠지지 않았으면 승인자만 운영으로 올린다.
    """
    _, llm = _scripted(monkeypatch)
    old = langfuse.add("type", tasks.TEMPLATES["type"], ["production"])
    staged = langfuse.add("type", EDITED, ["staging"])
    eng, appr = user(db, "ENGINEER"), user(db, "APPROVER")
    job = prompt_editor.start_eval(db, "type", eng, wait=True)
    job = client.get("/api/prompts/type/evaluations/latest").json()
    assert job["status"] == "DONE", job
    assert job["staging_version"] == staged and job["promote_block"] is None
    assert job["metrics"][0]["name"] == "유형 정확도" and job["metrics"][0]["now"] == 100.0
    # 기준선 값은 저장소 기준선 파일에서 읽는다(평가셋·기준선을 다시 만들어도 테스트를 고치지 않게)
    saved_base = json.loads((get_settings().seed_dir.parent / "eval" / "baseline.json").read_text())
    assert job["metrics"][0]["baseline"] == saved_base["metrics"]["type"]["accuracy"]["value"]
    assert all("유형 하나만 고른다." in p for p in llm.prompts)       # staging 판으로 물음
    saved = db.execute("SELECT prompt_versions->>'type', repeat FROM prompt_eval_run "
                       "WHERE eval_id = %s", (job["eval_id"],)).fetchone()
    assert saved == (f"{tasks.PROMPTS['type']}+lf{staged}", 3)
    # 엔지니어는 못 올림, 승인자는 올림
    r = client.post("/api/prompts/type/promote", headers=as_user(eng),
                    json={"job_id": job["job_id"]})
    assert r.status_code == 403
    r = client.post("/api/prompts/type/promote", headers=as_user(appr),
                    json={"job_id": job["job_id"]})
    assert r.status_code == 200 and r.json()["version"] == staged
    versions = langfuse.prompts["rfp-type"]
    assert "production" in versions[staged - 1]["labels"]
    assert "production" not in versions[old - 1]["labels"]


def test_regression_blocks_promote(db, client, langfuse, monkeypatch):
    """Scenario: 나빠진 판은 운영으로 못 올림 — 회귀면 이유가 남고 올리기를 거절."""
    public = pe.load_set(pe.find_set("public", get_settings()))
    wrong = sorted(i.id for i in public.items if i.role == "type" and not i.injection_of)
    _scripted(monkeypatch, wrong=set(wrong[:10]))
    langfuse.add("type", EDITED, ["staging"])
    job = prompt_editor.start_eval(db, "type", user(db, "ENGINEER"), wait=True)
    job = prompt_editor.latest_job("type")
    assert job["status"] == "DONE" and job["regression"] and "회귀" in job["promote_block"]
    r = client.post("/api/prompts/type/promote",
                    headers=as_user(user(db, "APPROVER")), json={"job_id": job["job_id"]})
    assert r.status_code == 409 and "회귀" in r.json()["detail"]


def test_staging_changed_after_eval(db, client, langfuse, monkeypatch):
    """Scenario: 평가 뒤 staging이 바뀌면 다시 평가 — 다른 판을 올리지 않음."""
    _scripted(monkeypatch)
    langfuse.add("type", EDITED, ["staging"])
    prompt_editor.start_eval(db, "type", user(db, "ENGINEER"), wait=True)
    job = prompt_editor.latest_job("type")
    langfuse.add("type", EDITED + " ", ["staging"])
    r = client.post("/api/prompts/type/promote",
                    headers=as_user(user(db, "APPROVER")), json={"job_id": job["job_id"]})
    assert r.status_code == 409 and "다시 평가" in r.json()["detail"]


def test_role_without_items_cannot_eval(db, langfuse):
    langfuse.add("handoff", tasks.TEMPLATES["handoff"], ["staging"])
    with pytest.raises(prompt_editor.EditorError, match="평가 문항이 없어"):
        prompt_editor.start_eval(db, "handoff", user(db, "ENGINEER"))


def test_ai_off_cannot_eval(db, client, langfuse, monkeypatch):
    """Scenario: AI를 끈 설정이면 평가 잠김 — 평가 요청은 거절(사용자 잘못 아님)."""
    monkeypatch.setattr(llm_client, "ai_mode", lambda settings: "OFF")
    langfuse.add("type", EDITED, ["staging"])
    assert client.get("/api/prompts/type").json()["ai_ready"] is False
    r = client.post("/api/prompts/type/evaluations", headers=as_user(user(db, "ENGINEER")),
                    json={})
    assert r.status_code == 409 and r.json()["detail"] == prompt_editor.AI_OFF
