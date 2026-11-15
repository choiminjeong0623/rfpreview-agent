"""Langfuse 프롬프트 관리 연동 (change add-langfuse-prompts, ADR-010).

명세 prompt-evaluation "Langfuse에서 프롬프트 가져오기", "평가를 통과한 판만 운영으로",
"Langfuse로 호출 기록 보내기"의 Scenario. 진짜 Langfuse 대신 같은 공개 API를 흉내 내는
가짜 서버(httpx MockTransport)를 쓴다.
"""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from rfp_agent.api.main import app
from rfp_agent.config import get_settings
from rfp_agent.llm import prompt_source, tasks
from rfp_agent.pipeline import ai_calls, langfuse_ops, prompt_registry
from tests.conftest import FakeLLM
from tests.test_prompt_versions import run


class FakeLangfuse:
    """Langfuse 공개 API 가운데 프롬프트(v2)와 OTLP 받기만. 표시는 프롬프트마다 한 버전에만."""

    def __init__(self):
        self.prompts: dict[str, list[dict]] = {}
        self.requests: list[httpx.Request] = []
        self.traces: list[dict] = []
        self.down = False

    def add(self, role: str, text: str, labels: list[str], code_version: str | None = None,
            message: str | None = None) -> int:
        name = prompt_source.name_of(role)
        versions = self.prompts.setdefault(name, [])
        for v in versions:
            v["labels"] = [x for x in v["labels"] if x not in labels]
        n = len(versions) + 1
        versions.append({"name": name, "type": "text", "prompt": text, "version": n,
                         "labels": list(labels), "tags": [],
                         "config": {"code_version": code_version or tasks.PROMPTS[role]},
                         "commitMessage": message})
        return n

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.down:
            raise httpx.ConnectError("연결 거부", request=request)
        assert request.headers["authorization"].startswith("Basic ")
        path = request.url.path
        if request.method == "GET" and path.startswith("/api/public/v2/prompts/"):
            name = path.rsplit("/", 1)[1]
            label = request.url.params.get("label", "production")
            hit = [v for v in self.prompts.get(name, []) if label in v["labels"]]
            return httpx.Response(200, json=hit[0]) if hit else httpx.Response(404, json={})
        if request.method == "POST" and path == "/api/public/v2/prompts":
            body = json.loads(request.content)
            role = body["name"].removeprefix(prompt_source.NAME_PREFIX)
            n = self.add(role, body["prompt"], body["labels"], body["config"]["code_version"],
                         body.get("commitMessage"))
            return httpx.Response(201, json=self.prompts[body["name"]][n - 1])
        if request.method == "PATCH" and "/versions/" in path:
            _, name, _, version = path.rsplit("/", 3)
            labels = json.loads(request.content)["newLabels"]
            for v in self.prompts[name]:
                v["labels"] = [x for x in v["labels"] if x not in labels]
            target = self.prompts[name][int(version) - 1]
            target["labels"] += labels
            return httpx.Response(200, json=target)
        if request.method == "POST" and path == "/api/public/otel/v1/traces":
            assert request.headers["x-langfuse-ingestion-version"] == "4"
            self.traces.append(json.loads(request.content))
            return httpx.Response(200, json={})
        return httpx.Response(404, json={})

    def gets(self) -> int:
        return sum(1 for r in self.requests if r.method == "GET")


def fake_langfuse(monkeypatch):
    """가짜 Langfuse를 켠다. 다른 시험 파일의 고정물도 이것을 쓴다."""
    fake = FakeLangfuse()
    monkeypatch.setenv("RFP_LANGFUSE", "on")
    monkeypatch.setenv("LANGFUSE_HOST", "http://langfuse.local:3000")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    get_settings.cache_clear()
    monkeypatch.setattr(prompt_source, "_transport", httpx.MockTransport(fake.handler))
    prompt_source.clear_cache()
    yield fake
    prompt_source.clear_cache()
    get_settings.cache_clear()          # 다음 시험이 켜 둔 설정을 쓰지 않게


@pytest.fixture
def langfuse(monkeypatch):
    yield from fake_langfuse(monkeypatch)
    get_settings.cache_clear()


EDITED = tasks.TEMPLATES["type"].replace("유형 하나를 고른다.", "유형 하나만 고른다.")


def test_off_uses_code_without_asking(monkeypatch):
    """Scenario: 끄면 코드 판 — Langfuse에 묻지 않고 코드 판·코드 틀을 쓴다."""
    calls = []
    monkeypatch.setattr(prompt_source, "_transport",
                        httpx.MockTransport(lambda r: calls.append(r) or httpx.Response(500)))
    found = prompt_source.resolve()
    assert prompt_source.versions(found) == tasks.PROMPTS
    assert all(r.source == "CODE" and r.fallback is None for r in found.values())
    assert calls == []


def test_langfuse_version_used_and_recorded(db, spec, langfuse):
    """Scenario: Langfuse 판을 씀.

    보낸 프롬프트가 그 판 글이고 실행 기록·재사용 열쇠에 버전이 남는다.
    """
    first = run(db, FakeLLM(), [spec])                 # 아직 Langfuse에 판 없음 → 코드 판
    assert first["prompt_versions"]["type"] == tasks.PROMPTS["type"]
    n = langfuse.add("type", EDITED, ["production"])
    prompt_source.clear_cache()
    llm = FakeLLM()
    second = run(db, llm, [spec])
    want = f"{tasks.PROMPTS['type']}+lf{n}"
    assert second["prompt_versions"]["type"] == want
    assert second["prompt_versions"]["risk"] == tasks.PROMPTS["risk"]
    assert any("유형 하나만 고른다." in p for p in llm.prompts)
    assert not any("유형 하나를 고른다." in p for p in llm.prompts)
    assert second["documents_reused"] == 0             # 문서 처리 역할 판이 바뀌어 다시 분석
    sources = db.execute("SELECT graph_state->'prompt_sources' FROM review_run WHERE run_id = %s",
                         (second["run_id"],)).fetchone()[0]
    assert sources["type"] == {"source": "LANGFUSE", "langfuse_version": n, "fallback": None}
    assert sources["classify"]["fallback"] == "NOT_FOUND"


@pytest.mark.parametrize("change,reason", [
    (lambda t: t.replace("{{document}}", ""), "PLACEHOLDERS"),
    (lambda t: t.replace(tasks.DATA_RULE, ""), "DATA_RULE"),
    (lambda t: t + "{{extra}}", "PLACEHOLDERS"),
])
def test_bad_langfuse_prompt_falls_back(langfuse, change, reason):
    """Scenario: 검사에 걸린 판은 코드 판 — 자리표시자·데이터 규칙이 어긋나면 그 역할만 코드 판."""
    langfuse.add("type", change(tasks.TEMPLATES["type"]), ["production"])
    langfuse.add("risk", tasks.TEMPLATES["risk"], ["production"])
    found = prompt_source.resolve()
    assert (found["type"].source, found["type"].fallback) == ("CODE", reason)
    assert found["type"].template == tasks.TEMPLATES["type"]
    assert found["risk"].source == "LANGFUSE"


def test_other_code_version_falls_back(langfuse, monkeypatch):
    """Scenario: 코드 판이 바뀌면 예전 Langfuse 판을 쓰지 않음."""
    langfuse.add("type", EDITED, ["production"])
    monkeypatch.setitem(tasks.PROMPTS, "type", "t99")
    prompt_source.clear_cache()
    found = prompt_source.resolve()
    assert (found["type"].version, found["type"].fallback) == ("t99", "CODE_VERSION")


def test_unreachable_falls_back_once(db, spec, langfuse):
    """Scenario: Langfuse에 닿지 못하면 코드 판.

    분석은 계속하고, 한 번만 묻고 나머지 역할은 묻지 않는다.
    """
    langfuse.down = True
    r = run(db, FakeLLM(), [spec])
    assert r["prompt_versions"] == tasks.PROMPTS
    assert langfuse.gets() == 1
    found = prompt_source.resolve()
    assert {x.fallback for x in found.values()} == {"UNREACHABLE"}


def test_no_keys_means_code(monkeypatch):
    monkeypatch.setenv("RFP_LANGFUSE", "on")
    monkeypatch.delenv("LANGFUSE_HOST", raising=False)
    monkeypatch.setenv("LANGFUSE_HOST", "")
    get_settings.cache_clear()
    prompt_source.clear_cache()
    try:
        assert {r.fallback for r in prompt_source.resolve().values()} == {"NOT_CONFIGURED"}
    finally:
        prompt_source.clear_cache()
        get_settings.cache_clear()


def test_run_keeps_its_snapshot(langfuse):
    """Scenario: 실행 중에는 같은 판 — 도중에 표시를 옮겨도 시작할 때 고른 판 (CR-11)."""
    langfuse.add("type", EDITED, ["production"])
    snap = prompt_source.resolve()
    langfuse.add("type", tasks.TEMPLATES["type"] + " ", ["production"])
    prompt_source.clear_cache()
    with prompt_source.use(snap):
        assert prompt_source.version_of("type").endswith("+lf1")
        llm = FakeLLM()
        tasks.type_unclassified(llm, ["Type tests shall be witnessed."])
        assert "유형 하나만 고른다." in llm.prompts[0]
    assert prompt_source.version_of("type").endswith("+lf2")


def test_render_does_not_refill_values():
    """채운 문서 본문 안의 {{…}}는 다시 채우지 않는다."""
    llm = FakeLLM()
    tasks.label_sentences(llm, "1. General", ["The value {{document}} shall be kept."])
    assert "The value {{document}} shall be kept." in llm.prompts[0]


def test_push_prompts_then_same(langfuse):
    """코드 틀을 staging으로 올리고, 같은 글이면 다시 올리지 않는다."""
    first = langfuse_ops.push_prompts("staging")
    assert {p.status for p in first} == {"NEW"} and len(first) == len(tasks.PROMPTS)
    stored = langfuse.prompts["rfp-type"][0]
    assert stored["prompt"] == tasks.TEMPLATES["type"] and stored["labels"] == ["staging"]
    assert stored["config"] == {"code_version": tasks.PROMPTS["type"]}
    assert {p.status for p in langfuse_ops.push_prompts("staging")} == {"SAME"}
    # 운영 표시가 없으니 운영 판은 코드 판
    assert {r.fallback for r in prompt_source.resolve().values()} == {"NOT_FOUND"}


def block(**kw):
    base = dict(label="staging", status="DONE", repeat=3, min_repeat=3, has_baseline=True,
                note=None, regression=False, candidates=["x"])
    return langfuse_ops.promote_block(**(base | kw))


def test_promote_rules():
    """Scenario: 평가를 통과한 판만 운영으로 — 회귀·기준선 없음·반복 부족·운영 판 평가는 막는다."""
    assert block() is None
    assert "회귀" in block(regression=True)
    assert "기준선" in block(has_baseline=False)
    assert "기준선" in block(note="기준선 다시 만들기 필요 (평가셋 판이 다름)")
    assert "--repeat 3" in block(repeat=1)
    assert "staging" in block(label="production")
    assert "코드 판" in block(candidates=[])


def test_promote_moves_production_label(langfuse, monkeypatch):
    """staging에서 평가한 판 묶음 가운데 Langfuse 판에 production을 붙인다."""
    old = langfuse.add("type", tasks.TEMPLATES["type"], ["production"])
    new = langfuse.add("type", EDITED, ["staging"])
    monkeypatch.setenv("RFP_LANGFUSE_LABEL", "staging")
    get_settings.cache_clear()
    staged = prompt_source.resolve(fresh=True)
    done = langfuse_ops.promote(langfuse_ops.promotable(staged))
    assert done == [f"type {tasks.PROMPTS['type']}+lf{new}"]
    versions = langfuse.prompts["rfp-type"]
    assert "production" in versions[new - 1]["labels"]
    assert "production" not in versions[old - 1]["labels"]


def test_push_traces_links_prompt(db, spec, langfuse):
    """Scenario: Langfuse로 호출 기록 보내기.

    원문 없이 보내고, Langfuse 판으로 부른 호출은 그 버전과 잇는다.
    """
    n = langfuse.add("type", EDITED, ["production"])
    r = run(db, FakeLLM(), [spec])
    sent = langfuse_ops.push_traces(db, r["run_id"])
    assert sent and len(langfuse.traces) == 1
    spans = langfuse.traces[0]["resourceSpans"][0]["scopeSpans"][0]["spans"]
    attrs = [{a["key"]: a["value"] for a in s["attributes"]} for s in spans]
    typed = [a for a in attrs if a["rfp.role"]["stringValue"] == "type"]
    assert typed and all(a["langfuse.observation.prompt.name"]["stringValue"] == "rfp-type"
                         and a["langfuse.observation.prompt.version"]["intValue"] == str(n)
                         for a in typed)
    others = [a for a in attrs if a["rfp.role"]["stringValue"] != "type"]
    assert all("langfuse.observation.prompt.name" not in a for a in others)
    body = json.dumps(langfuse.traces[0], ensure_ascii=False)
    assert "shall" not in body                         # 원문 없이 해시만
    assert ai_calls.otel(db, r["run_id"]) == langfuse.traces[0]


def test_prompt_view_and_health_show_source(db, db_url, langfuse, monkeypatch):
    """Scenario: 프롬프트 관리 화면에 가져온 곳 — 역할마다 Langfuse 버전이나 코드로 돌아간 이유."""
    n = langfuse.add("type", EDITED, ["production"])
    langfuse.add("risk", tasks.TEMPLATES["risk"].replace(tasks.DATA_RULE, ""), ["production"])
    body = prompt_registry.overview(db)
    roles = {r["role"]: r for r in body["roles"]}
    assert (roles["type"]["prompt_source"], roles["type"]["langfuse_version"]) == ("LANGFUSE", n)
    assert roles["type"]["current"] == f"{tasks.PROMPTS['type']}+lf{n}"
    assert roles["risk"]["prompt_source"] == "CODE"
    assert roles["risk"]["fallback"] == prompt_source.FALLBACKS["DATA_RULE"]
    assert body["doc_key"].endswith(f"+lf{n}")
    assert body["langfuse"] == {"enabled": True, "label": "production",
                                "host": "http://langfuse.local:3000"}
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    health = TestClient(app).get("/api/health").json()
    assert (health["prompt_source"], health["prompt_label"]) == ("LANGFUSE", "production")
    api = TestClient(app).get("/api/prompts").json()
    assert "secret" not in json.dumps(api) and "sk-lf" not in json.dumps(api)
