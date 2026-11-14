"""AI 사용 방식 설정: Gemini · 사내 모델 · AI 끄기.

change add-ai-mode, 명세 review-run·service-health.
"""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from rfp_agent.api.main import app
from rfp_agent.config import Settings, get_settings
from rfp_agent.llm import client, tasks
from rfp_agent.llm.client import CONFIG_FAILURE_MESSAGE, LLMConfigError, LocalLLM, make_llm
from rfp_agent.pipeline import meaning
from rfp_agent.pipeline.run import RunContext, create_run, execute_run
from tests.conftest import FakeLLM
from tests.docx_factory import build_gis_spec

VERSION = "test-dict-v1"
URL = "http://llm.internal.test/v1"


def local(handler, embed_model=None):
    """사내 모델 대역: 요청은 MockTransport로만 간다 (밖으로 나가지 않음)."""
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    llm = LocalLLM(URL, "qwen-internal", "secret-token", embed_model,
                   transport=httpx.MockTransport(record))
    return llm, seen


def chat_answer(content: dict) -> httpx.Response:
    return httpx.Response(200, json={
        "choices": [{"message": {"content": json.dumps(content)}}],
        "usage": {"prompt_tokens": 120, "completion_tokens": 8}})


def test_ai_off_sends_nothing(db, tmp_path, monkeypatch):
    """Scenario: AI 끄기 — 키가 있어도 요청 0건, 규칙만으로 담당자 확인, 실행 기록 모델 없음."""
    def explode(*args, **kwargs):
        raise AssertionError("AI 끄기인데 Gemini 클라이언트를 만듦")

    monkeypatch.setattr(client, "GeminiLLM", explode)
    settings = Settings(gemini_api_key="real-looking-key", rfp_ai_mode="off")
    assert client.ai_mode(settings) == "OFF"
    llm = make_llm(settings)
    assert llm is None
    run_id = create_run(db, VERSION, llm)
    path = build_gis_spec(tmp_path / "synthetic_154kV_GIS_spec.docx")
    assert execute_run(RunContext(db, VERSION, llm, None), run_id, [path]) == "ENGINEER_REVIEW"
    model, calls = db.execute("SELECT llm_model, llm_calls FROM review_run WHERE run_id = %s",
                              (run_id,)).fetchone()
    assert (model, calls) == (None, 0)


def test_local_model_receives_requests(db):
    """Scenario: 사내 모델로 보냄 — 요청은 정한 주소로만, 실행 기록 모델은 사내 모델 이름."""
    llm, seen = local(lambda r: chat_answer({"doc_kind": "REQUIREMENT_SPEC"}))
    assert tasks.classify_document(llm, "spec.docx", "TECHNICAL SPECIFICATION") == \
        "REQUIREMENT_SPEC"
    [request] = seen
    assert str(request.url) == f"{URL}/chat/completions"
    assert request.headers["authorization"] == "Bearer secret-token"
    body = json.loads(request.content)
    assert body["model"] == "qwen-internal" and body["temperature"] == 0
    assert body["response_format"]["json_schema"]["schema"]["required"] == ["doc_kind"]
    assert (llm.usage.input_tokens, llm.usage.output_tokens) == (120, 8)

    run_id = create_run(db, VERSION, llm)
    model = db.execute("SELECT llm_model FROM review_run WHERE run_id = %s",
                       (run_id,)).fetchone()[0]
    assert model == "qwen-internal"

    settings = Settings(rfp_ai_mode="local", rfp_local_llm_url=URL,
                        rfp_local_llm_model="qwen-internal")
    assert isinstance(make_llm(settings), LocalLLM)
    assert client.ai_model(settings) == "qwen-internal"


@pytest.mark.parametrize("code", [401, 404])
def test_local_model_config_error_stops(code):
    """Scenario: 사내 모델 설정 오류 — 다시 묻지 않고 설정 확인 문구로 멈춘다."""
    llm, seen = local(lambda r: httpx.Response(code, text="no"))
    with pytest.raises(LLMConfigError, match=CONFIG_FAILURE_MESSAGE):
        tasks.classify_document(llm, "spec.docx", "x")
    assert len(seen) == 1


def test_local_server_error_is_retried():
    """사내 서버 오류(503)는 정해진 횟수만 다시 묻는다 (CR-12)."""
    answers = iter([httpx.Response(503), chat_answer({"doc_kind": "TEST_SPEC"})])
    llm, seen = local(lambda r: next(answers))
    assert tasks.classify_document(llm, "spec.docx", "x") == "TEST_SPEC"
    assert len(seen) == 2


def test_local_embeddings():
    """사내 벡터 모델이 있으면 /embeddings로 받고 index 순서로 맞춘다."""
    def handler(request):
        assert json.loads(request.content)["model"] == "bge-internal"
        return httpx.Response(200, json={"data": [{"index": 1, "embedding": [0.0, 1.0]},
                                                  {"index": 0, "embedding": [1.0, 0.0]}]})

    llm, seen = local(handler, "bge-internal")
    assert llm.embed(["a", "b"]) == [[1.0, 0.0], [0.0, 1.0]]
    assert str(seen[0].url) == f"{URL}/embeddings"
    assert meaning.model_of(llm) == "bge-internal"


def test_local_without_embed_model_skips_meaning(db, tmp_path):
    """Scenario: 사내 벡터 모델 없음 — 뜻 찾기 "건너뜀", 분석은 담당자 확인 단계."""
    llm = FakeLLM()
    sender, seen = local(lambda r: httpx.Response(500))
    llm.embed = sender.embed            # 문장 쓰기는 대역, 벡터만 사내 모델 (벡터 모델 없음)
    llm.embed_model = None
    path = build_gis_spec(tmp_path / "synthetic_154kV_GIS_spec.docx")
    run_id = create_run(db, VERSION, llm)
    assert execute_run(RunContext(db, VERSION, llm, None), run_id, [path]) == "ENGINEER_REVIEW"
    assert meaning.status(db, run_id) == "SKIPPED"
    assert seen == []                   # 벡터 요청은 보내지도 않음


@pytest.mark.parametrize(("env", "mode", "model", "external"), [
    ({"GEMINI_API_KEY": "gm-secret", "RFP_AI_MODE": "gemini"}, "GEMINI", "gemini-3.8-flash", True),
    ({"RFP_AI_MODE": "local", "RFP_LOCAL_LLM_URL": URL, "RFP_LOCAL_LLM_MODEL": "qwen-internal",
      "RFP_LOCAL_LLM_KEY": "lc-secret"}, "LOCAL", "qwen-internal", False),
    ({"GEMINI_API_KEY": "gm-secret", "RFP_AI_MODE": "off"}, "OFF", None, False),
])
def test_health_shows_ai_mode(monkeypatch, env, mode, model, external):
    """Scenario: AI 방식 표시 — ai_mode·external_send, 응답에 키·주소 글자 없음."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://nobody@127.0.0.1:1/none")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.8-flash")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    try:
        response = TestClient(app).get("/api/health")
    finally:
        get_settings.cache_clear()
    body = response.json()
    assert (body["ai_mode"], body["ai_model"], body["external_send"]) == (mode, model, external)
    assert body["llm_configured"] is (mode != "OFF")
    for secret in ("gm-secret", "lc-secret", "llm.internal"):
        assert secret not in response.text
