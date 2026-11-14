"""AI 문장 구분에서 협조 요청 유형 문장 지키기 (change update-ai-label-keep-handoff).

명세 requirement-extraction "AI 문장 구분에서 묻지 않는 문장"의 Scenario.
합성 RFP 28을 AI로 분석했을 때 작성 규칙으로 옮겨져 견적 협조 요청이 빠진 문장(8.1)을 쓴다.
"""

from docx import Document

from rfp_agent.pipeline import dictionaries
from rfp_agent.pipeline.document import HANDOFF_TYPES, process_document
from tests.conftest import FakeLLM

VERSION = "test-dict-v1"
LABEL = "RFP의 한 절에서"
PRICE = ("The evaluated price shall state the currency, price validity period and payment "
         "milestones for the complete scope of supply.")
TEST = "Type Test reports issued by an independent accredited laboratory shall be submitted."
QUAL = "The manufacturer shall hold a valid ISO 9001 certificate for the production facility."
COMMITTEE = "The Evaluation Committee shall score compliant proposals using the weight model below."


class AllWritingRules(FakeLLM):
    """문장 구분 질문에는 모두 작성 규칙이라고 답하는 대역."""

    def generate_json(self, prompt: str, schema: dict) -> dict:
        answer = super().generate_json(prompt, schema)
        if "labels" in answer:
            answer["labels"] = [{"n": a["n"], "v": "WRITING_RULE"} for a in answer["labels"]]
        return answer


def spec(path):
    doc = Document()
    doc.add_paragraph("TECHNICAL SPECIFICATION")
    doc.add_paragraph("8. QUOTATION, QUALITY AND SUPPLIER QUALIFICATION")
    for text in (PRICE, TEST, QUAL, COMMITTEE):
        doc.add_paragraph(text)
    for n in range(8):
        doc.add_paragraph(f"Clause {n + 1}: the scoring sheet shall be kept by the committee.")
    doc.save(str(path))
    return path


def lines(db, document_id):
    rows = db.execute(
        """SELECT q.text_raw, q.req_kind,
                  (SELECT t.type_code FROM requirement_type_tag t
                    WHERE t.requirement_id = q.requirement_id AND t.is_primary)
             FROM requirement q WHERE q.document_id = %s""", (document_id,)).fetchall()
    return {text: (kind, primary) for text, kind, primary in rows}


def test_handoff_type_sentence_kept(db, tmp_path):
    """Scenario: 협조 요청 유형 문장 — AI에 묻지 않고 요구사항, 주 유형 비용 영향."""
    llm = AllWritingRules()
    result = process_document(db, spec(tmp_path / "spec.docx"), dictionaries.load(db), VERSION,
                              llm, None)
    got = lines(db, result.document_id)
    assert got[PRICE] == ("REQUIREMENT", "COST")
    assert got[TEST] == ("REQUIREMENT", "TEST")
    assert got[QUAL] == ("REQUIREMENT", "MAKER_QUAL")
    asked = "\n".join(p for p in llm.prompts if LABEL in p)
    assert asked and not any(s in asked for s in (PRICE, TEST, QUAL))


def test_other_sentence_follows_ai(db, tmp_path):
    """Scenario: 유형 낱말이 없는 문장 — AI 답대로 작성 규칙."""
    llm = AllWritingRules()
    result = process_document(db, spec(tmp_path / "spec.docx"), dictionaries.load(db), VERSION,
                              llm, None)
    assert lines(db, result.document_id)[COMMITTEE][0] == "WRITING_RULE"
    assert COMMITTEE in "\n".join(p for p in llm.prompts if LABEL in p)


def test_handoff_types_match_reference_table(db):
    """협조 요청 유형 상수 = 기준표에서 담당이 엔지니어가 아닌 유형."""
    rows = db.execute("SELECT type_code FROM requirement_type WHERE default_role <> 'ENGINEER'")
    assert {code for (code,) in rows} == HANDOFF_TYPES
