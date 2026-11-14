"""의무 표현이 없는 요구 줄 뽑기 (change update-extract-recall).

명세 requirement-extraction "의무 표현이 없는 요구 줄"의 Scenario.
합성 RFP 28에서 놓쳤던 줄 모양을 쓴다.
"""

from docx import Document

from rfp_agent.pipeline import dictionaries
from rfp_agent.pipeline.extract import extract
from rfp_agent.pipeline.reader import read_document
from rfp_agent.pipeline.run import RunContext, create_run, execute_run
from rfp_agent.pipeline.structure import build_tables, find_sections

VERSION = "test-dict-v1"
HEADER = ["ID", "Requirement", "Required Bidder Response", "Status"]
ROWS = [["T1", "Product identity", "Product code, name, family and product datasheet", "Mandatory"],
        ["T2", "Electrical rating", "Rated voltage, rated current and short-circuit capability",
         "Mandatory"],
        ["T3", "Standards", "Current applicable standards and verifiable certificates",
         "Mandatory where applicable"]]
ITEM = "Manufacturer product datasheet and a complete bill of materials for every offered item."
HEADER_LINE = "Volume IV Technical Specification Chapter 3"
NO_DEVIATIONS = ("No deviations from the technical requirements will be accepted "
                 "after contract award.")


def spec(path):
    doc = Document()
    doc.add_paragraph("REQUEST FOR PROPOSAL")
    doc.add_heading("1. Procurement Objective", level=1)
    doc.add_paragraph("Each bidder shall identify eligible products and provide evidence.")
    doc.add_heading("2. Mandatory Proposal Submission", level=1)
    doc.add_paragraph(ITEM)
    doc.add_paragraph("Completed Excel response matrix for every offered product.")
    doc.add_paragraph(HEADER_LINE)                 # 문서에 두 번 나오는 머리말
    doc.add_paragraph("Page 24 / 42")              # 짧은 쪽 번호 줄
    doc.add_heading("3. Technical Requirements", level=1)
    table = doc.add_table(rows=0, cols=4)
    for row in [HEADER, *ROWS]:
        for cell, text in zip(table.add_row().cells, row, strict=True):
            cell.text = text
    doc.add_paragraph(HEADER_LINE)
    doc.add_heading("4. Deviations and Contract Conditions", level=1)
    doc.add_paragraph(NO_DEVIATIONS)
    for n in range(6):
        doc.add_paragraph(f"Clause {n + 1}: the contractor shall keep the records listed here.")
    doc.save(str(path))
    return path


def candidates(db, path):
    dicts = dictionaries.load(db)
    blocks = read_document(path)
    tables = build_tables(blocks, dicts.column_roles)
    return extract(blocks, find_sections(blocks), tables, frozenset(),
                   [e.pattern for e in dicts.risk_expressions])


def requirement_texts(found):
    return [c.text for c in found if c.req_kind == "REQUIREMENT"]


def test_status_column_table(db, tmp_path):
    """Scenario: 상태 칸이 있는 요구 표 — "Mandatory" 3줄은 후보, 머리 줄은 아님."""
    found = candidates(db, spec(tmp_path / "rfp.docx"))
    rows = [c for c in found if c.rule_id == "E-STATUS-ROW"]
    assert [c.text.split(" | ")[0] for c in rows] == ["T1", "T2", "T3"]
    assert not any("Required Bidder Response" in t for t in requirement_texts(found))


def test_submission_list_item(db, tmp_path):
    """Scenario: 제출물 목록 절 — 의무 표현이 없는 목록 줄도 후보."""
    found = candidates(db, spec(tmp_path / "rfp.docx"))
    items = {c.text: c.rule_id for c in found}
    assert items[ITEM] == "E-SUBMISSION-ITEM"


def test_repeated_header_lines(db, tmp_path):
    """Scenario: 머리말 반복 줄 — 반복되는 머리말과 짧은 쪽 번호 줄은 후보가 아님."""
    texts = [c.text for c in candidates(db, spec(tmp_path / "rfp.docx"))]
    assert HEADER_LINE not in texts and "Page 24 / 42" not in texts


def test_risk_sentence(db, tmp_path):
    """Scenario: 위험 표현 문장 — 의무 표현 없이도 후보, 처리하면 포괄 조항 후보."""
    path = spec(tmp_path / "rfp.docx")
    found = {c.text: (c.req_kind, c.rule_id) for c in candidates(db, path)}
    assert found[NO_DEVIATIONS] == ("REQUIREMENT", "E-RISK-SENTENCE")
    run_id = create_run(db, VERSION, None)
    execute_run(RunContext(db, VERSION, None, None), run_id, [path])
    kinds = [k for (k,) in db.execute(
        "SELECT f.risk_kind FROM risk_flag f JOIN risk_flag_member m USING (risk_id) "
        "JOIN requirement q USING (requirement_id) WHERE f.run_id = %s AND q.text_raw = %s",
        (run_id, NO_DEVIATIONS))]
    assert "BLANKET" in kinds
