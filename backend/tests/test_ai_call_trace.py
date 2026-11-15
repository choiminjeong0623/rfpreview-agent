"""AI 호출 기록 (change add-ai-call-trace, FR-21·NFR-14).

명세 review-run "AI 호출 기록"·"원문 없는 호출 기록"·"같은 입력, 다른 답"·
"실행 기록 화면의 AI 호출"·"OpenTelemetry 형식 내보내기"의 Scenario. AI는 대역(FakeLLM)이다.
"""

import pytest

from rfp_agent.config import get_settings
from rfp_agent.llm import tasks, trace
from rfp_agent.llm.evidence import EvidenceSpan
from rfp_agent.pipeline import ai_calls
from rfp_agent.pipeline.run import RunContext, create_run, execute_run
from tests.conftest import FakeLLM

VERSION = "test-dict-v1"


def calls_of(conn, run_id):
    conn.commit()
    return ai_calls.calls(conn, run_id)


def analysed(conn, spec, llm) -> int:
    run_id = create_run(conn, VERSION, llm)
    assert execute_run(RunContext(conn, VERSION, llm, None), run_id, [spec],
                       {spec.name: {"bundle": "B"}}) == "ENGINEER_REVIEW"
    return run_id


def test_call_count_matches_run_log(db, spec):
    """Scenario: 호출 기록 수와 실행 기록 — 호출 기록 수 = 실행 기록의 AI 호출 수(재시도 포함)."""
    run_id = analysed(db, spec, FakeLLM())
    rows = calls_of(db, run_id)
    llm_calls = db.execute("SELECT llm_calls FROM review_run WHERE run_id = %s",
                           (run_id,)).fetchone()[0]
    assert rows and len(rows) == llm_calls
    assert "type" in {r["role"] for r in rows}
    first = rows[0]
    assert first["step"] == "documents" and first["model"] == "fake-model"
    assert first["prompt_version"] == tasks.PROMPTS[first["role"]]
    assert first["result"] == "OK" and len(first["input_hash"]) == 16 and first["batch_lines"] >= 0


class BadTypes(FakeLLM):
    """유형 묶음에 줄 번호가 모자란 답 (형식 오류)."""

    def generate_json(self, prompt, schema):
        data = super().generate_json(prompt, schema)
        if "types" in data:
            data["types"] = data["types"][:-1] or [{"n": 99, "v": "NONE"}]
        return data


def test_format_error_call(db, spec):
    """Scenario: 형식이 틀린 답 — 그 호출의 결과는 형식 오류이고 처리 단계가 보인다."""
    run_id = create_run(db, VERSION, None)
    execute_run(RunContext(db, VERSION, BadTypes(), None), run_id, [spec],
                {spec.name: {"bundle": "B"}})             # 한 줄짜리도 틀리면 분석은 실패한다
    bad = [r for r in calls_of(db, run_id) if r["result"] == "FORMAT_ERROR"]
    assert bad and all(r["role"] == "type" and r["step"] == "documents" for r in bad)


class UnknownEvidence(FakeLLM):
    def generate_json(self, prompt, schema):
        self.prompts.append(prompt)
        return {"claims": [{"text": "확인이 필요하다.", "exact_quote": "rated",
                            "evidence_ids": ["E-9-9"], "relation": "INFERRED"}]}


def test_dropped_answer(db):
    """Scenario: 코드 검사로 버린 답 — 결과는 성공, 버린 이유가 보인다."""
    run_id = create_run(db, VERSION, None)
    with trace.session(run_id, "analysis") as s:
        trace.set_step("risks")
        out = tasks.explain_risk(UnknownEvidence(), "BLANKET", "표현: deemed",
                                 [EvidenceSpan("E-1-1", "The switchgear shall be rated 145 kV.")])
        trace.flush(db, s)
    assert out.reason == tasks.UNKNOWN_EVIDENCE
    [row] = calls_of(db, run_id)
    assert (row["result"], row["dropped_reason"], row["step"], row["role"]) == \
        ("OK", "UNKNOWN_EVIDENCE", "risks", "risk")


def test_hashes_only_by_default(db, spec):
    """Scenario: 기본 설정은 해시만 — 원문 표가 비고, 호출 기록에 원문이 없다."""
    run_id = analysed(db, spec, FakeLLM())
    assert db.execute("SELECT count(*) FROM ai_call_raw").fetchone()[0] == 0
    leaked = db.execute("SELECT count(*) FROM ai_call WHERE run_id = %s AND "
                        "row_to_json(ai_call)::text ~* '(shall|switchgear|kV)'",
                        (run_id,)).fetchone()[0]
    assert leaked == 0


def test_raw_purged_after_keep_days(db, monkeypatch):
    """Scenario: 보관 기간이 지난 원문 — 원문만 지워지고 호출 기록은 남는다."""
    monkeypatch.setenv("RFP_TRACE_RAW", "on")
    get_settings.cache_clear()
    try:
        run_id = create_run(db, VERSION, None)
        with trace.session(run_id, "analysis") as s:
            tasks.classify_document(FakeLLM(), "spec.docx", "TECHNICAL SPECIFICATION")
            trace.flush(db, s)
        db.commit()
        assert db.execute("SELECT count(*) FROM ai_call_raw").fetchone()[0] == 1
        db.execute("UPDATE ai_call_raw SET created_at = now() - make_interval(days => %s)",
                   (trace.RAW_KEEP_DAYS + 1,))
        assert trace.purge(db) == 1
        assert db.execute("SELECT count(*) FROM ai_call_raw").fetchone()[0] == 0
        assert len(calls_of(db, run_id)) == 1
    finally:
        get_settings.cache_clear()


class Kind(FakeLLM):
    def __init__(self, kind):
        super().__init__()
        self.kind = kind

    def generate_json(self, prompt, schema):
        return {"doc_kind": self.kind}


def test_same_input_different_answer(db):
    """Scenario: 같은 문서를 두 번 분석 — 두 번째 검토에 다른 답 1."""
    first, second = create_run(db, VERSION, None), create_run(db, VERSION, None)
    for run_id, kind in ((first, "TEST_SPEC"), (second, "BID_FORM")):
        with trace.session(run_id, "analysis") as s:
            tasks.classify_document(Kind(kind), "spec.docx", "TECHNICAL SPECIFICATION")
            tasks.classify_document(Kind("BOQ"), "boq.docx", "BILL OF QUANTITIES")
            trace.flush(db, s)
    db.commit()
    assert ai_calls.different_answers(db, second) == 1
    assert ai_calls.summary(db, second)["different_answers"] == 1


def test_slow_calls_listed(db, spec):
    """Scenario: 느린 호출 찾기 — 호출마다 걸린 시간과 단계별 AI 시간 합을 돌려준다."""
    run_id = analysed(db, spec, FakeLLM())
    s = ai_calls.summary(db, run_id)
    assert s["count"] == len(s["calls"]) and all(c["duration_ms"] >= 0 for c in s["calls"])
    assert {x["step"] for x in s["step_ms"]} >= {"documents"}
    assert sum(x["ms"] for x in s["step_ms"]) == sum(c["duration_ms"] for c in s["calls"])


def test_ai_calls_response_shape(db, spec):
    """Scenario: AI를 켠 검토의 호출 목록 — 호출 기록이 있어도 응답 모양(AiCalls)과 맞는다.

    run_token은 OpenTelemetry 내보내기에만 쓰고 화면 응답에는 싣지 않는다 (update-runlog-detail).
    """
    from rfp_agent.api.schemas import AiCalls

    run_id = analysed(db, spec, FakeLLM())
    s = ai_calls.summary(db, run_id)
    assert s["count"] > 0 and all("run_token" not in c for c in s["calls"])
    AiCalls.model_validate(s)


def test_otel_span_per_call(db):
    """Scenario: 호출마다 span — 호출 3건이면 span 3개, 속성에 역할·모델·판·토큰."""
    run_id = create_run(db, VERSION, None)
    with trace.session(run_id, "analysis") as s:
        for name in ("a.docx", "b.docx", "c.docx"):
            tasks.classify_document(FakeLLM(), name, "TECHNICAL SPECIFICATION")
        trace.flush(db, s)
    db.commit()
    [res] = ai_calls.otel(db, run_id)["resourceSpans"]
    spans = res["scopeSpans"][0]["spans"]
    assert len(spans) == 3
    for span in spans:
        keys = {a["key"] for a in span["attributes"]}
        assert {"rfp.role", "gen_ai.request.model", "rfp.prompt_version",
                "gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens"} <= keys
    assert len({sp["traceId"] for sp in spans}) == 1


@pytest.mark.parametrize("raw", ["off", "on"])
def test_health_trace_raw(raw, monkeypatch):
    """원문 저장이 켜져 있으면 상태 점검에 안내 문장 (명세 "원문 없는 호출 기록")."""
    from fastapi.testclient import TestClient

    from rfp_agent.api.main import app

    monkeypatch.setenv("RFP_TRACE_RAW", raw)
    get_settings.cache_clear()
    try:
        body = TestClient(app).get("/api/health").json()
    finally:
        get_settings.cache_clear()
    assert body["trace_raw"] is (raw == "on")
    assert (body["trace_raw_warning"] is not None) is (raw == "on")
