"""검토 도우미 (change add-review-assistant, 명세 review-assistant)."""

import pytest

from rfp_agent.llm.client import Usage
from rfp_agent.pipeline import assistant
from rfp_agent.pipeline.review import ReviewError
from rfp_agent.pipeline.run import RunContext, create_run, execute_run
from tests.docx_factory import build_gis_spec

VERSION = "test-dict-v1"
SENTENCE = "The maximum ambient temperature for the GIS enclosure shall be 40 °C."


class ScriptLLM:
    """정해 둔 단계를 차례로 내는 가짜 AI. steps의 값이 함수면 지금 프롬프트로 부른다."""

    model = "fake-model"

    def __init__(self, steps, fail=False, error=None):
        self.steps = list(steps)
        self.prompts: list[str] = []
        self.usage = Usage()
        self.fail = fail
        self.error = error

    def generate_json(self, prompt, schema):
        self.prompts.append(prompt)
        if self.error is not None:
            raise self.error
        if self.fail:
            raise TimeoutError("응답 시간 초과")
        step = self.steps.pop(0)
        return step(prompt) if callable(step) else step


@pytest.fixture
def run(db, spec, tmp_path):
    gis = build_gis_spec(tmp_path / "synthetic_154kV_GIS_spec.docx")
    run_id = create_run(db, VERSION, None)
    assert execute_run(RunContext(db, VERSION, None, None), run_id, [gis, spec]) == \
        "ENGINEER_REVIEW"
    return run_id


def ref_in(prompt: str, text: str) -> str:
    """프롬프트의 관찰 줄에서 text가 들어간 줄의 근거 번호."""
    line = next(x for x in prompt.splitlines() if text in x and x.startswith("["))
    return line[1:line.index("]")]


def answer(text, ref_text):
    return lambda p: {"action": "answer",
                      "sentences": [{"text": text, "evidence_ids": [ref_in(p, ref_text)]}]}


def test_answer_with_evidence(db, run):
    """Scenario: 근거와 함께 답하기 — 문장 하나, 그 줄의 원문·위치, 찾은 경로."""
    llm = ScriptLLM([
        {"action": "search_requirements", "words": "ambient temperature enclosure"},
        answer("GIS 외함 최고 주변 온도는 40 °C로 정해져 있습니다.", "enclosure"),
    ])
    out = assistant.ask(db, run, "주변 온도 조건", llm)
    assert out["mode"] == "AI" and out["dropped"] == 0 and out["note"] is None
    [s] = out["sentences"]
    [e] = out["evidence"]
    assert s["evidence_ids"] == [e["ref"]] and e["text_raw"] == SENTENCE
    assert e["kind"] == "REQUIREMENT" and e["locations"]
    assert out["steps"] == [{"tool": "search_requirements",
                             "words": "ambient temperature enclosure", "type_code": None,
                             "result": None, "ref": None, "found": 1}]
    assert "읽기만" in llm.prompts[0]


def test_find_judgments_reads_only(db, run):
    """Scenario: 판정 찾기 — 근거 줄에 판정 값·요구값, 판정은 그대로."""
    before = db.execute("SELECT count(*), sum(judgment_id), string_agg(result, ',' ORDER BY "
                        "judgment_id) FROM judgment WHERE run_id = %s", (run,)).fetchone()
    [result] = db.execute("SELECT result FROM judgment WHERE run_id = %s AND is_current "
                          "ORDER BY judgment_id LIMIT 1", (run,)).fetchone()

    def cite_first(p):
        line = next(x for x in p.splitlines() if x.startswith("[J"))
        return {"action": "answer", "sentences": [
            {"text": "이 판정을 먼저 보세요.", "evidence_ids": [line[1:line.index("]")]]}]}

    llm = ScriptLLM([{"action": "find_judgments", "result": result}, cite_first])
    out = assistant.ask(db, run, "먼저 볼 판정", llm)
    [e] = out["evidence"]
    assert e["kind"] == "JUDGMENT" and e["result"] == result and e["judgment_id"]
    assert out["steps"][0]["tool"] == "find_judgments" and out["steps"][0]["result"] == result
    assert "요구값" in llm.prompts[1]
    after = db.execute("SELECT count(*), sum(judgment_id), string_agg(result, ',' ORDER BY "
                       "judgment_id) FROM judgment WHERE run_id = %s", (run,)).fetchone()
    assert before == after


def test_processing_run_rejected(db):
    """Scenario: 분석 중인 검토 — 409."""
    run_id = create_run(db, VERSION, None)
    with pytest.raises(ReviewError) as err:
        assistant.ask(db, run_id, "주변 온도", ScriptLLM([]))
    assert err.value.status == 409


def test_unknown_evidence_dropped(db, run):
    """Scenario: 주지 않은 근거 번호 — 그 문장만 빠지고 뺀 문장 1개."""
    def two(p):
        good = ref_in(p, "enclosure")
        return {"action": "answer", "sentences": [
            {"text": "외함 온도 조건이 있습니다.", "evidence_ids": [good]},
            {"text": "다른 조항도 있습니다.", "evidence_ids": ["R999999"]}]}

    llm = ScriptLLM([{"action": "search_requirements", "words": "enclosure"}, two])
    out = assistant.ask(db, run, "외함 온도", llm)
    assert [s["text"] for s in out["sentences"]] == ["외함 온도 조건이 있습니다."]
    assert out["dropped"] == 1


def test_number_not_in_evidence_dropped(db, run):
    """Scenario: 근거에 없는 숫자 — 그 문장은 빠지고 남는 문장이 없으면 근거를 찾지 못함."""
    llm = ScriptLLM([
        {"action": "search_requirements", "words": "enclosure"},
        answer("외함 최고 주변 온도는 45 °C입니다.", "enclosure"),
    ])
    out = assistant.ask(db, run, "외함 온도", llm)
    assert out["sentences"] == [] and out["evidence"] == []
    assert out["dropped"] == 1 and out["note"] == assistant.NOT_FOUND


def test_no_ai_key_searches_words(db, run):
    """Scenario: AI 키 없음 — 두 낱말이 들어간 줄과 위치만, 문장 없음, 안내."""
    out = assistant.ask(db, run, "ambient temperature", None)
    assert out["mode"] == "SEARCH" and out["sentences"] == []
    texts = [e["text_raw"] for e in out["evidence"]]
    assert SENTENCE in texts and len(texts) == 2          # 외함 40 °C, 케이블 50 °C
    assert all("ambient temperature" in t for t in texts)
    assert all(e["locations"] for e in out["evidence"])
    assert out["note"] == assistant.NO_AI == "AI를 쓰지 않는 설정"


class InvalidKeyError(Exception):
    """google.genai ClientError처럼 code가 붙은 키 오류."""

    code = 401


def test_ai_config_error_falls_back(db, run):
    """Scenario: AI 설정 오류 — 글자로 찾은 줄과 "AI 키·모델 설정 오류 — 설정 확인"."""
    llm = ScriptLLM([], error=InvalidKeyError("API key not valid"))
    out = assistant.ask(db, run, "ambient temperature", llm)
    assert out["mode"] == "SEARCH" and out["note"] == assistant.AI_CONFIG
    assert out["note"] == "AI 키·모델 설정 오류 — 설정 확인"
    assert len(out["evidence"]) == 2
    assert len(llm.prompts) == 1                          # 설정 오류는 다시 묻지 않음


def test_ai_failure_falls_back(db, run):
    """Scenario: AI가 답하지 못함 — 재시도 뒤에도 답이 없으면 글자로 찾은 줄과 까닭 (CR-12)."""
    out = assistant.ask(db, run, "ambient temperature", ScriptLLM([], fail=True))
    assert out["mode"] == "SEARCH" and out["note"] == assistant.AI_FAILED == "AI가 답하지 못함"
    assert len(out["evidence"]) == 2


def test_search_note_is_reason_only(db, run):
    """맞는 줄이 없어도 note에는 까닭만 (0건 안내는 화면이 한다)."""
    out = assistant.ask(db, run, "시험 입회 조건이 있는 조항", None)
    assert out["evidence"] == [] and out["note"] == assistant.NO_AI


def test_search_limit_then_answer(db, run):
    """세 번 찾은 뒤에는 답만 받는다 (도구 목록 없이)."""
    search = {"action": "search_requirements", "words": "shall"}
    llm = ScriptLLM([search, search, search, {"action": "answer", "sentences": []}])
    out = assistant.ask(db, run, "모든 조항", llm)
    assert len(out["steps"]) == 3 and out["note"] == assistant.NOT_FOUND
    assert "더 찾을 수 없다" in llm.prompts[-1]


def test_api(db, run, db_url, monkeypatch):
    """API: AI 키 없이 묻기, 짧은 질문 400."""
    from fastapi.testclient import TestClient

    from rfp_agent.api.main import app
    from rfp_agent.config import get_settings

    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("GEMINI_API_KEY", "")
    get_settings.cache_clear()
    try:
        client = TestClient(app)
        res = client.post(f"/api/runs/{run}/assistant", json={"question": "ambient temperature"})
        assert res.status_code == 200, res.text
        assert res.json()["mode"] == "SEARCH" and len(res.json()["evidence"]) == 2
        assert client.post(f"/api/runs/{run}/assistant", json={"question": "a"}).status_code == 400
    finally:
        get_settings.cache_clear()
