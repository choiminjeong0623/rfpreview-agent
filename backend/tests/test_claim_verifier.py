"""위험 설명 검증 에이전트 (change add-claim-verifier).

명세 evidence-integrity "AI 설명 검증", review-run "검증 확인 필요 건수"의 Scenario.
"""

from rfp_agent.llm import tasks
from rfp_agent.pipeline import queries
from rfp_agent.pipeline.run import RunContext, create_run, execute_run
from rfp_agent.pipeline.run_log import run_log
from tests.conftest import FakeLLM
from tests.docx_factory import build_gis_spec

VERSION = "test-dict-v1"


class VerdictLLM(FakeLLM):
    """검증 질문에 정해 둔 답을 낸다. bad=True면 번호를 겹쳐 낸다."""

    def __init__(self, verdict="YES", bad=False):
        super().__init__()
        self.verdict, self.bad = verdict, bad

    def generate_json(self, prompt, schema):
        answer = super().generate_json(prompt, schema)
        if "verdicts" in answer:
            answer["verdicts"] = [{"n": a["n"], "v": self.verdict} for a in answer["verdicts"]]
            if self.bad:
                answer["verdicts"].append({"n": 0, "v": "YES"})
        return answer


def run_gis(conn, tmp_path, llm):
    gis = build_gis_spec(tmp_path / "synthetic_154kV_GIS_spec.docx")
    run_id = create_run(conn, VERSION, llm)
    assert execute_run(RunContext(conn, VERSION, llm, None), run_id, [gis]) == "ENGINEER_REVIEW"
    return run_id


def claim_statuses(conn, run_id):
    return {s for (s,) in conn.execute("SELECT status FROM claim_evidence WHERE run_id = %s",
                                       (run_id,))}


def test_all_supported(seeded_db, tmp_path):
    """Scenario: 모두 받쳐 줌 — 검증 통과, 문장마다 SUPPORTED."""
    llm = VerdictLLM("YES")
    run_id = run_gis(seeded_db, tmp_path, llm)
    risks = queries.run_risks(seeded_db, run_id)
    assert risks and all(r["explanation_check"] == "VERIFIED" for r in risks)
    assert claim_statuses(seeded_db, run_id) == {"SUPPORTED"}
    verify_prompts = [p for p in llm.prompts if "검증자" in p]
    assert len(verify_prompts) == len(risks)
    assert all("사실:" not in p for p in verify_prompts)     # 사실 문장은 주지 않는다


def test_unsupported_sentence(seeded_db, tmp_path):
    """Scenario: 받쳐 주지 않는 문장 · Scenario: 검증 확인 필요 건수."""
    run_id = run_gis(seeded_db, tmp_path, VerdictLLM("NO"))
    risks = queries.run_risks(seeded_db, run_id)
    assert risks and all(r["explanation_ai"] and r["explanation_check"] == "NEEDS_REVIEW"
                         for r in risks)
    assert claim_statuses(seeded_db, run_id) == {"NEEDS_REVIEW"}
    [log] = [r for r in run_log(seeded_db) if r["run_id"] == run_id]
    assert log["explanations_unverified"] == len(risks)


def test_bad_verdict_format(seeded_db, tmp_path):
    """Scenario: 검증 답 형식 오류 — 다시 묻지 않고 확인 필요."""
    llm = VerdictLLM("YES", bad=True)
    run_id = run_gis(seeded_db, tmp_path, llm)
    risks = queries.run_risks(seeded_db, run_id)
    assert risks and all(r["explanation_check"] == "NEEDS_REVIEW" for r in risks)
    assert len([p for p in llm.prompts if "검증자" in p]) == len(risks)
    assert llm.usage.retries == 0


def test_check_support_unit():
    claims = (tasks.Claim("누설 기준이 다르다.", "0.5 %", ("E-1-1",), "DIRECT"),
              tasks.Claim("다른 조항은 1 %다.", "1 %", ("E-1-2",), "DIRECT"))
    sources = {"E-1-1": "Leakage 0.5 % per year.", "E-1-2": "Leakage 1 % per year."}
    llm = VerdictLLM("UNSURE")
    assert tasks.check_support(llm, claims, sources) == ["UNSURE", "UNSURE"]
    assert "[E-1-2] Leakage 1 % per year." in llm.prompts[0]
    no_check = tasks.RiskExplanation("t", claims)
    assert no_check.check is None
