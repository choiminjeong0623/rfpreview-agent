"""합성 docx로 검토 실행 전체(문서 처리 → 쌍 후보 → 위험 조건)를 DB까지 돌린다.

명세 review-run, evidence-integrity, risk-detection, document-intake(판독 불가)의 Scenario.
"""

import pytest

from rfp_agent.llm.client import FAILURE_MESSAGE
from rfp_agent.pipeline import queries
from rfp_agent.pipeline.run import RunContext, create_run, execute_run
from tests.conftest import FakeLLM
from tests.docx_factory import build_gis_spec, build_image_only

VERSION = "test-dict-v1"


@pytest.fixture
def spec_docx(tmp_path):
    return build_gis_spec(tmp_path / "synthetic_154kV_GIS_spec.docx")


def run_once(conn, paths, llm=None):
    ctx = RunContext(conn, VERSION, llm, None)
    run_id = create_run(conn, VERSION, llm)
    stage = execute_run(ctx, run_id, paths)
    return run_id, stage


def scalar(conn, sql, *params):
    return conn.execute(sql, params).fetchone()[0]


def test_run_records_version_and_moves_to_engineer_review(seeded_db, spec_docx):
    """Scenario: 파일 1로 검토 시작."""
    run_id, stage = run_once(seeded_db, [spec_docx])
    assert stage == "ENGINEER_REVIEW"
    summary = queries.run_summary(seeded_db, run_id)
    assert summary["dict_version"] == VERSION
    assert summary["documents"] == 1 and summary["llm_model"] is None
    doc = queries.run_documents(seeded_db, run_id)[0]
    # 파일 목록에 없는 문서는 판정하지 않는 묶음(C)으로 두고 사람이 확인한다.
    assert (doc["bundle"], doc["judge_target"], doc["needs_review"]) == ("C", False, True)


def test_every_requirement_has_a_location(seeded_db, spec_docx):
    """Scenario: 위치가 없는 값."""
    run_id, _ = run_once(seeded_db, [spec_docx])
    reqs = queries.run_requirements(seeded_db, run_id, limit=500)
    assert reqs and all(r["locations"] for r in reqs)
    short_time = next(r for r in reqs if "short-time" in r["text_raw"])
    [loc] = short_time["locations"]
    assert (loc["table_name"], loc["item_no"]) == ("TS-154-GIS", "2")
    [value] = short_time["values"]
    assert (float(value["num_value"]), value["unit_raw"], float(value["cond_time_s"]),
            value["item_key"]) == (40, "kA", 1, "short_time_current")


def test_redacted_and_formula_values(seeded_db, spec_docx):
    run_id, _ = run_once(seeded_db, [spec_docx])
    reqs = queries.run_requirements(seeded_db, run_id, limit=500)
    [redacted] = next(r for r in reqs if "auxiliary" in r["text_raw"])["values"]
    assert (redacted["cell_form"], redacted["num_value"], redacted["flag"]) == (
        "EMPTY", None, "REDACTED")
    [formula] = next(r for r in reqs if "peak withstand" in r["text_raw"])["values"]
    assert formula["cell_form"] == "FORMULA" and float(formula["num_value"]) == 100


def test_type_tags(seeded_db, spec_docx):
    run_id, _ = run_once(seeded_db, [spec_docx])
    tests = queries.run_requirements(seeded_db, run_id, type_code="TEST")
    assert any("Type Test Report" in r["text_raw"] for r in tests)
    primary = next(t for t in tests[0]["types"] if t["is_primary"])
    assert primary["type_code"] == "TEST" and primary["rule_code"].startswith("T-TEST")


class WritingRuleLLM(FakeLLM):
    """문장을 모두 작성 규칙이라고 답하는 언어 모델 대역."""

    def generate_json(self, prompt: str, schema: dict) -> dict:
        answer = super().generate_json(prompt, schema)
        if "labels" in answer:
            answer["labels"] = [{"n": a["n"], "v": "WRITING_RULE"} for a in answer["labels"]]
        return answer


def test_deemed_kept_when_ai_says_writing_rule(seeded_db, spec_docx):
    """Scenario: deemed to be accepted.

    언어 모델이 문장을 작성 규칙이라고 답해도 포괄 조항 후보 1건이 나온다.
    """
    run_id, _ = run_once(seeded_db, [spec_docx], llm=WritingRuleLLM())
    blanket = [r for r in queries.run_risks(seeded_db, run_id) if r["risk_kind"] == "BLANKET"]
    assert len(blanket) == 1
    assert "deemed" in blanket[0]["facts"]


def test_risk_candidates(seeded_db, spec_docx):
    """Scenario: including but not limited to · Scenario: 겹치는 열린 표현.

    "including but not limited to"는 사전의 두 표현에 걸려도 범위 모호 1건이다.
    """
    run_id, _ = run_once(seeded_db, [spec_docx])
    risks = queries.run_risks(seeded_db, run_id)
    kinds = sorted(r["risk_kind"] for r in risks)
    assert kinds == ["BLANKET", "OPEN_SCOPE", "VALUE_MISMATCH"]
    assert all(r["status"] == "CANDIDATE" for r in risks)
    mismatch = next(r for r in risks if r["risk_kind"] == "VALUE_MISMATCH")
    # 표의 <0.5 %(GIS)와 문장의 1 %(차단기). 같은 문장의 "압력저하 3 %"는 가스 누설이 아니다.
    assert mismatch["item_key"] == "gas_leakage_rate"
    assert "적용 대상이 다름" in mismatch["facts"]
    assert sorted(m["value_raw"] for m in mismatch["members"]) == ["1 % 이내", "<0.5"]


def test_same_document_twice_gives_same_results(seeded_db, spec_docx):
    """Scenario: 같은 문서 두 번."""
    first, _ = run_once(seeded_db, [spec_docx])
    second, _ = run_once(seeded_db, [spec_docx])
    a, b = (queries.run_summary(seeded_db, r) for r in (first, second))
    assert (a["requirements"], a["risks"]) == (b["requirements"], b["risks"])
    docs = {queries.run_documents(seeded_db, r)[0]["document_id"] for r in (first, second)}
    assert len(docs) == 1                   # 같은 판이면 저장된 처리 결과를 다시 쓴다
    facts = [[x["facts"] for x in queries.run_risks(seeded_db, r)] for r in (first, second)]
    assert facts[0] == facts[1]


def test_same_name_different_content_is_processed_again(seeded_db, tmp_path):
    """Scenario: 이름이 같고 내용이 다른 파일 —
    이름·파일 번호가 같아도 내용이 다르면 저장된 처리 결과를 다시 쓰지 않는다."""
    from docx import Document

    name = "RFP_product_master_based_EN.docx"      # 파일 목록 23번
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    old = build_gis_spec(tmp_path / "a" / name)
    new = build_gis_spec(tmp_path / "b" / name)
    doc = Document(str(new))
    doc.add_paragraph("The GIS shall be designed for indoor installation.")
    doc.save(str(new))

    first, _ = run_once(seeded_db, [old])
    second, _ = run_once(seeded_db, [new])
    third, _ = run_once(seeded_db, [new])
    a, b, c = (queries.run_documents(seeded_db, r)[0] for r in (first, second, third))
    assert a["file_no"] == b["file_no"]             # 문서 목록의 같은 번호
    assert a["document_id"] != b["document_id"]     # 내용이 다르면 새로 처리
    assert b["document_id"] == c["document_id"]     # 같은 내용이면 다시 쓴다


def test_ai_failure_stops_run_with_message(seeded_db, spec_docx):
    """Scenario: 계속 실패."""
    run_id, stage = run_once(seeded_db, [spec_docx], llm=FakeLLM(fail=True))
    summary = queries.run_summary(seeded_db, run_id)
    assert stage == "FAILED" == summary["stage"]
    assert summary["failed_step"] == "documents"
    assert summary["error_message"] == FAILURE_MESSAGE


def test_ai_inputs_are_per_section(seeded_db, spec_docx):
    """Scenario: 가장 긴 문서."""
    llm = FakeLLM()
    run_id, stage = run_once(seeded_db, [spec_docx], llm=llm)
    assert stage == "ENGINEER_REVIEW"
    assert queries.run_summary(seeded_db, run_id)["llm_model"] == "fake-model"
    label_prompts = [p for p in llm.prompts if "절 제목:" in p]
    assert label_prompts
    for prompt in label_prompts:
        assert prompt.count("절 제목:") == 1
        assert "TS-154-GIS" not in prompt    # 문서를 통째로 넣지 않는다
    explained = [r for r in queries.run_risks(seeded_db, run_id) if r["explanation_ai"]]
    assert explained


def test_risk_explanation_keeps_claim_evidence(seeded_db, spec_docx):
    """Scenario: 근거와 맞는 설명 저장 — 문장마다 인용과 근거 위치가 남는다."""
    run_id, _ = run_once(seeded_db, [spec_docx], llm=FakeLLM())
    rows = seeded_db.execute(
        """SELECT c.target_id, c.claim_text, c.exact_quote, c.status, s.location_id,
                  EXISTS (SELECT 1 FROM risk_flag_member m
                          JOIN requirement_location rl USING (requirement_id)
                          WHERE m.risk_id = c.target_id AND rl.location_id = s.location_id)
           FROM claim_evidence c JOIN claim_evidence_source s USING (claim_id)
           WHERE c.run_id = %s AND c.target_table = 'risk_flag'""", (run_id,)).fetchall()
    explained = [r for r in queries.run_risks(seeded_db, run_id) if r["explanation_ai"]]
    assert rows and len({r[0] for r in rows}) == len(explained)
    assert all(r[2] and r[3] == "SUPPORTED" and r[5] for r in rows)


def test_unreadable_document_skips_later_steps(seeded_db, tmp_path):
    path = build_image_only(tmp_path / "scan_only.docx")
    run_id, stage = run_once(seeded_db, [path])
    assert stage == "ENGINEER_REVIEW"
    doc = queries.run_documents(seeded_db, run_id)[0]
    assert (doc["readable"], doc["language"], doc["requirements"]) == (False, "image", 0)
    assert scalar(seeded_db, "SELECT count(*) FROM section WHERE document_id = %s",
                  doc["document_id"]) == 0
