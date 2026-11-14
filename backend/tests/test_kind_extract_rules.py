"""문서 종류별 추출 규칙 (change add-kind-extract-rules, C1).

명세 requirement-extraction "문서 종류별 추출 규칙"의 Scenario.
"""

from pathlib import Path

from docx import Document

from rfp_agent.pipeline import dictionaries
from rfp_agent.pipeline.document import process_document

VERSION = "test-dict-v1"
RATING = "Short circuit current rating: 200 kAIC."
FORM = "Each Bidder must fill out this form."
RISKY = "Each Bidder must fill out this form, including but not limited to the schedules."


def supplier(path: Path, marks: bool = True) -> Path:
    """공급사 답안: 표시 머리, 표시가 있는 조항, shall도 표시도 없는 조항 줄, 제목 줄."""
    doc = Document()
    for n in range(10):
        doc.add_paragraph(f"Section 26 20 00 electric distribution, part {n + 1} of the answer.")
    table = doc.add_table(rows=0, cols=3)
    rows = [["SECTION 26", "C: Complied D: Deviation E: Exclusion" if marks else "SECTION", ""],
            ["C" if marks else "", "A.", "Panelboard bussing and lugs shall be copper."],
            ["D" if marks else "", "B.", "Cabinets shall be rated NEMA 3R with padlock."],
            ["", "", "RATINGS"],
            ["", "C.", RATING]]
    for values in rows:
        for cell, value in zip(table.add_row().cells, values, strict=True):
            cell.text = value
    doc.save(str(path))
    return path


def letters(path: Path, *sentences: str) -> Path:
    doc = Document()
    doc.add_paragraph("FORMS")
    for n in range(10):
        doc.add_paragraph(f"Clause {n + 1}: the contractor shall keep the records listed here.")
    for s in sentences:
        doc.add_paragraph(s)
    doc.save(str(path))
    return path


def requirements(conn, path):
    result = process_document(conn, path, dictionaries.load(conn), VERSION, None, None)
    return conn.execute("SELECT text_raw, req_kind, source_kind, supplier_mark, rule_id "
                        "FROM requirement WHERE document_id = %s", (result.document_id,)).fetchall()


def find(rows, text):
    return [r for r in rows if text in r[0]]


def test_unmarked_clause_in_answer_table(db, tmp_path):
    """Scenario: 표시 없는 답안 표 조항 줄 — 공급사 답안 후보, 표시는 비어 있음."""
    rows = requirements(db, supplier(tmp_path / "Comment Update answer.docx"))
    [(_, kind, source, mark, rule)] = find(rows, RATING)
    assert (kind, source, mark) == ("REQUIREMENT", "SUPPLIER_ANSWER", None)
    assert rule == "E-MARK-TABLE-ROW"
    assert find(rows, "Panelboard bussing")[0][3] == "C"            # 표시가 있는 줄은 그대로
    assert not find(rows, "RATINGS")                                 # 제목 줄은 아님


def test_supplier_spec_without_marks(db, tmp_path):
    """Scenario: 표시가 없는 공급사 사양서 — 표 조항 줄을 답안 후보로 더하지 않는다."""
    rows = requirements(db, supplier(tmp_path / "Comment Update answer.docx", marks=False))
    assert not find(rows, RATING)
    assert not [r for r in rows if r[2] == "SUPPLIER_ANSWER"]


def test_bid_form_note_is_writing_rule(db, tmp_path):
    """Scenario: 입찰 서식 작성 안내 — 입찰 서식은 작성 규칙, 요구 사양서는 요구사항."""
    bid = requirements(db, letters(tmp_path / "Bidding Forms_notes.docx", FORM))
    assert find(bid, FORM)[0][1:5:3] == ("WRITING_RULE", "E-FORM-NOTE")
    spec = requirements(db, letters(tmp_path / "general_specification.docx", FORM))
    assert find(spec, FORM)[0][1] == "REQUIREMENT"


def test_bid_form_note_with_risk_expression(db, tmp_path):
    """Scenario: 위험 표현이 든 작성 안내 — 요구사항으로 남는다."""
    rows = requirements(db, letters(tmp_path / "Bidding Forms_notes.docx", RISKY))
    assert find(rows, "including but not limited to")[0][1] == "REQUIREMENT"
