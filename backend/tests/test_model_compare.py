"""여러 회사 모델 비교 평가.

명세 prompt-evaluation의 Scenario (change add-model-compare, FR-23). AI는 대역이다.
"""

import json
from types import SimpleNamespace

import httpx
import pytest

from rfp_agent.llm import client as llm_client
from rfp_agent.llm.client import (
    NO_KEY,
    NOT_ALLOWED,
    AnthropicLLM,
    HTTPStatusFailure,
    LLMConfigError,
    LocalLLM,
    ModelSpec,
    call_with_retry,
    make_compare_llm,
    parse_models,
    strict_schema,
)
from rfp_agent.pipeline import prompt_eval as pe
from rfp_agent.pipeline import run_log
from tests.test_prompt_eval import Scripted, answers_for, jsonl, type_item


def evalset(n: int = 6, name: str = "cmp") -> pe.EvalSet:
    return pe.parse_set(name, jsonl([type_item(i) for i in range(n)]))


def maker(llms: dict[str, object], calls: list | None = None):
    """공급자:모델 → 대역. 없으면 키 없음. calls에 만들기 요청을 적는다."""
    def make(spec, settings, private_set=False):
        if calls is not None:
            calls.append(spec.label)
        if private_set and spec.provider not in llm_client.PRIVATE_OK:
            return None, NOT_ALLOWED
        llm = llms.get(spec.label)
        return (llm, None) if llm is not None else (None, NO_KEY)
    return make


def settings_stub(**kw):
    base = dict(rfp_llm_workers=2, rfp_llm_timeout_s=5, gemini_api_key=None,
                anthropic_api_key=None, openai_api_key=None, rfp_local_llm_url=None,
                rfp_local_llm_key=None)
    return SimpleNamespace(**(base | kw))


# ── 모델 목록과 공급자 ───────────────────────────────────────────────────

def test_parse_models():
    specs = parse_models("gemini:gemini-3.8-flash, local:qwen2.5:7b,anthropic:claude-haiku-5-5")
    assert [s.label for s in specs] == ["gemini:gemini-3.8-flash", "local:qwen2.5:7b",
                                        "anthropic:claude-haiku-5-5"]
    assert specs[1].model == "qwen2.5:7b"                         # 첫 ':'에서만 나눔
    for bad in ("gpt-x", "foo:bar", "", "gemini:a,gemini:a"):
        with pytest.raises(ValueError):
            parse_models(bad)


def test_make_compare_llm_reasons():
    """키 없음·외부 전송 허용 안 됨은 클라이언트를 만들지 않는다."""
    s = settings_stub(openai_api_key="k", rfp_local_llm_url="http://llm.local/v1")
    assert make_compare_llm(ModelSpec("anthropic", "claude-haiku-5-5"), s) == (None, NO_KEY)
    assert make_compare_llm(ModelSpec("gemini", "g"), s) == (None, NO_KEY)
    llm, why = make_compare_llm(ModelSpec("openai", "gpt-x"), s)
    assert why is None and isinstance(llm, LocalLLM) and llm.temperature is None
    assert make_compare_llm(ModelSpec("openai", "gpt-x"), s, private_set=True) == \
        (None, NOT_ALLOWED)
    llm, why = make_compare_llm(ModelSpec("local", "qwen2.5:7b"), s, private_set=True)
    assert why is None and llm.temperature == 0


def test_openai_omits_temperature():
    """OpenAI는 temperature를 보내지 않고, 사내 local은 0을 보낸다."""
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"a": 1}'}}],
                                         "usage": {"prompt_tokens": 3, "completion_tokens": 1}})
    for temp in (None, 0):
        llm = LocalLLM("http://x/v1", "m", transport=httpx.MockTransport(handler),
                       temperature=temp)
        assert llm.generate_json("q", {"type": "object"}) == {"a": 1}
    assert "temperature" not in seen[0] and seen[1]["temperature"] == 0


class FakeMessages:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.requests = []

    def create(self, **kw):
        self.requests.append(kw)
        out = self.outcomes.pop(0)
        if isinstance(out, Exception):
            raise out
        return out


def anthropic_reply(text: str, stop: str = "end_turn"):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason=stop,
                           usage=SimpleNamespace(input_tokens=12, output_tokens=3))


def status_error(code: int):
    import anthropic

    response = httpx.Response(code, request=httpx.Request("POST", "https://api.anthropic.com"))
    return anthropic.APIStatusError("오류", response=response, body=None)


def test_anthropic_structured_output():
    """구조화 출력으로 묻고, 모든 object에 additionalProperties false, temperature는 없음."""
    fake = FakeMessages([anthropic_reply('{"types": [{"n": 0, "v": "TEST"}]}')])
    llm = AnthropicLLM("k", "claude-haiku-5-5", client=SimpleNamespace(messages=fake))
    schema = {"type": "object", "properties": {"types": {"type": "array", "items": {
        "type": "object", "properties": {"n": {"type": "integer"}}}}}}
    assert llm.generate_json("q", schema) == {"types": [{"n": 0, "v": "TEST"}]}
    req = fake.requests[0]
    sent = req["output_config"]["format"]["schema"]
    assert sent["additionalProperties"] is False
    assert sent["properties"]["types"]["items"]["additionalProperties"] is False
    assert "additionalProperties" not in schema                    # 원본은 그대로
    assert "temperature" not in req and req["model"] == "claude-haiku-5-5"
    assert llm.usage.input_tokens == 12 and llm.usage.output_tokens == 3
    assert strict_schema({"type": "string"}) == {"type": "string"}


def test_anthropic_errors_follow_retry_kinds():
    """429는 재시도, 401은 설정 오류로 바로 멈춤, 거절(빈 답)은 형식 오류."""
    ok = anthropic_reply('{"x": 1}')
    fake = FakeMessages([status_error(429), ok])
    llm = AnthropicLLM("k", "m", client=SimpleNamespace(messages=fake))
    assert call_with_retry(llm, "q", {"type": "object"}, lambda d: None) == {"x": 1}
    assert llm.usage.retries == 1

    fake = FakeMessages([status_error(401)])
    llm = AnthropicLLM("k", "m", client=SimpleNamespace(messages=fake))
    with pytest.raises(LLMConfigError):
        call_with_retry(llm, "q", {"type": "object"}, lambda d: None)
    assert len(fake.requests) == 1

    fake = FakeMessages([anthropic_reply("", stop="refusal")])
    llm = AnthropicLLM("k", "m", client=SimpleNamespace(messages=fake))
    with pytest.raises(llm_client.LLMFormatError):
        call_with_retry(llm, "q", {"type": "object"}, lambda d: None)
    assert isinstance(HTTPStatusFailure(429, "x"), RuntimeError)


# ── 비교 실행 ────────────────────────────────────────────────────────────

def test_compare_with_missing_key():
    """Scenario: 키가 없는 모델이 섞인 비교."""
    s = evalset()
    a = Scripted(answers_for(s), model="gemini-3.8-flash")
    b = Scripted(answers_for(s, wrong={"t000"}), model="qwen2.5:7b")
    specs = parse_models("gemini:gemini-3.8-flash,anthropic:claude-haiku-5-5,local:qwen2.5:7b")
    cmp = pe.compare_models(s, specs, None, make=maker({specs[0].label: a, specs[2].label: b}))
    status = {r.label: (r.status, r.skip_reason) for r in cmp.results}
    assert status == {"gemini:gemini-3.8-flash": ("DONE", None),
                      "anthropic:claude-haiku-5-5": ("SKIPPED", NO_KEY),
                      "local:qwen2.5:7b": ("DONE", None)}
    done = [r for r in cmp.results if r.status == "DONE"]
    assert all(r.latency_p50_ms is not None and r.latency_p95_ms is not None for r in done)
    assert done[0].cost_krw is not None and done[0].provider == "gemini"
    text = pe.compare_report(s, cmp)
    assert "건너뜀(키 없음)" in text and "p95" in text and "| 유형 정확도 |" in text
    assert len(a.prompts) == 6 and len(b.prompts) == 6


def test_compare_config_error_keeps_others():
    """Scenario: 한 모델의 설정 오류 — 그 모델은 답 없음, 다른 모델 결과는 남는다."""
    class Broken(Scripted):
        def generate_json(self, prompt, schema):
            self.prompts.append(prompt)
            raise HTTPStatusFailure(401, "키 틀림")

    s = evalset()
    good = Scripted(answers_for(s), model="gemini-3.8-flash")
    specs = parse_models("openai:gpt-x,gemini:gemini-3.8-flash")
    cmp = pe.compare_models(s, specs, None, make=maker({specs[0].label: Broken(model="gpt-x"),
                                                        specs[1].label: good}))
    broken, ok = cmp.results
    assert broken.status == "DONE" and broken.metrics["type"]["no_answer"]["min"] == 100
    assert ok.metrics["type"]["accuracy"]["min"] == 100
    assert cmp.cheapest is ok


def test_comparison_saved_as_one_group(db, db_url, monkeypatch):
    """Scenario: 비교 기록 묶음 — 같은 비교 묶음 번호와 각자의 공급자, API에 보임."""
    from fastapi.testclient import TestClient

    from rfp_agent.api.main import app
    from rfp_agent.config import get_settings

    s = evalset(name="grp")
    specs = parse_models("gemini:gemini-3.8-flash,local:qwen2.5:7b")
    cmp = pe.compare_models(s, specs, None, make=maker({
        specs[0].label: Scripted(answers_for(s), model="gemini-3.8-flash"),
        specs[1].label: Scripted(answers_for(s), model="qwen2.5:7b")}))
    compare_id = pe.save_comparison(db, cmp)
    db.commit()
    rows = pe.runs(db, "grp")
    assert {r["compare_id"] for r in rows} == {compare_id}
    assert {r["provider"] for r in rows} == {"gemini", "local"}
    assert all(r["latency_p95_ms"] is not None and not r["is_baseline"] for r in rows)
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    try:
        body = TestClient(app).get("/api/prompt-evals", params={"set": "grp"}).json()
        assert {(r["provider"], r["compare_id"]) for r in body["runs"]} == \
            {("gemini", compare_id), ("local", compare_id)}
    finally:
        get_settings.cache_clear()


def test_latency_percentiles():
    """Scenario: 응답 시간 기록 — 100·200·300·900밀리초면 p50 200, p95 900."""
    assert pe.nearest_rank([300, 100, 900, 200], 50) == 200
    assert pe.nearest_rank([300, 100, 900, 200], 95) == 900
    assert pe.nearest_rank([], 50) is None and pe.nearest_rank([7], 95) == 7

    s = evalset(4)
    waits = {f"line {n} ": ms for n, ms in enumerate((100, 200, 300, 900))}
    clock = {"now": 0.0}

    class Timed(Scripted):
        def generate_json(self, prompt, schema):
            clock["now"] += next(ms for k, ms in waits.items() if k in prompt) / 1000
            return super().generate_json(prompt, schema)

    monkeypatch_time = pytest.MonkeyPatch()
    monkeypatch_time.setattr(pe.time, "monotonic", lambda: clock["now"])
    monkeypatch_time.setattr(pe, "workers_of", lambda llm: 1)
    try:
        result = pe.evaluate(s, Timed(answers_for(s)), "GEMINI")
    finally:
        monkeypatch_time.undo()
    assert [a.ms for a in result.answers[0]] == [100, 200, 300, 900]
    assert (result.latency_p50_ms, result.latency_p95_ms) == (200, 900)


def fake_result(label: str, acc: float, cost: int | None, p95: int = 100,
                injection: bool = False) -> pe.EvalResult:
    provider, model = label.split(":")
    r = pe.EvalResult("DONE", evalset(1), model, provider.upper(), 1, provider=provider)
    r.metrics = {"type": {"accuracy": {"min": acc}}}
    r.cost_krw, r.latency_p95_ms = cost, p95
    r.injection_hits = ["x"] if injection else []
    return r


def test_cheapest_same_quality():
    """Scenario: 싸고 품질이 같은 모델 — A 90 %·300원, B 89 %·50원, C 70 %·10원, 문턱 2 %p → B."""
    a, b, c = fake_result("x:A", 90, 300), fake_result("y:B", 89, 50), fake_result("z:C", 70, 10)
    pick, note = pe.cheapest([a, b, c], 2)
    assert pick is b and "y:B" in note
    d = fake_result("w:D", 90, 40, injection=True)                  # 주입 영향이 있으면 제외
    assert pe.cheapest([a, b, c, d], 2)[0] is b


def test_cheapest_unknown_price():
    """Scenario: 단가를 모르는 모델 — 최고 모델의 단가를 모르고 다른 모델은 문턱 밖이면
    고를 수 없음."""
    pick, note = pe.cheapest([fake_result("local:Q", 95, None), fake_result("x:B", 80, 5)], 2)
    assert pick is None and note.startswith("고를 수 없음") and "단가" in note


def test_private_set_refuses_external(settings, tmp_path):
    """Scenario: 비공개 평가셋과 외부 모델 — anthropic은 요청 0건으로 건너뜀, local은 평가."""
    private = settings.private_data_dir / "eval" / "x.jsonl"
    assert pe.is_private_set(private, settings)
    assert not pe.is_private_set(tmp_path / "public.jsonl", settings)
    s = evalset()
    claude = Scripted(answers_for(s), model="claude-haiku-5-5")
    local = Scripted(answers_for(s), model="qwen2.5:7b")
    specs = parse_models("anthropic:claude-haiku-5-5,local:qwen2.5:7b")
    cmp = pe.compare_models(s, specs, None, private_set=True,
                            make=maker({specs[0].label: claude, specs[1].label: local}))
    assert (cmp.results[0].status, cmp.results[0].skip_reason) == ("SKIPPED", NOT_ALLOWED)
    assert claude.prompts == [] and len(local.prompts) == 6


def test_total_cost_cap():
    """Scenario: 합계가 상한을 넘는 비교 — 하나하나는 상한 아래여도 합이 넘으면
    아무도 부르지 않음."""
    s = evalset(30)
    one = pe.estimate(s.items, 1, "gemini-3.8-flash")["cost_krw"]
    two = pe.estimate(s.items, 1, "claude-haiku-5-5")["cost_krw"]
    cap = max(one, two)
    assert one + two > cap
    a = Scripted(answers_for(s), model="gemini-3.8-flash")
    b = Scripted(answers_for(s), model="claude-haiku-5-5")
    specs = parse_models("gemini:gemini-3.8-flash,anthropic:claude-haiku-5-5")
    make = maker({specs[0].label: a, specs[1].label: b})
    with pytest.raises(pe.EvalError, match=r"합계 어림 비용 .*상한 .*--yes"):
        pe.compare_models(s, specs, None, max_krw=cap, make=make)
    assert a.prompts == [] and b.prompts == []
    cmp = pe.compare_models(s, specs, None, max_krw=cap, confirmed=True, make=make)
    assert all(r.status == "DONE" for r in cmp.results)


def test_eval_prices_setting(monkeypatch):
    """RFP_EVAL_PRICES로 단가 표에 없는 모델의 단가(팀 가정)를 준다."""
    from rfp_agent.config import get_settings

    assert run_log.parse_prices("gpt-x=0.4/1.6; bad; q=1/x;qwen2.5:7b=0/0") == \
        {"gpt-x": (0.4, 1.6), "qwen2.5:7b": (0.0, 0.0)}
    monkeypatch.setenv("RFP_EVAL_PRICES", "gpt-x=1/2")
    get_settings.cache_clear()
    try:
        assert run_log.estimated_cost_krw("gpt-x", 1_000_000, 1_000_000, 0) == 4500
        assert run_log.estimated_cost_krw("claude-haiku-5-5", 1_000_000, 0, 0) == 150
    finally:
        get_settings.cache_clear()


def test_cli_models_with_baseline_refused(capsys):
    from rfp_agent.db import cli

    with pytest.raises(SystemExit):
        cli.main(["eval-prompts", "--set", "public", "--models", "gemini:g", "--baseline"])
    assert "기준선" in capsys.readouterr().err
