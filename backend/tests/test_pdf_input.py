"""PDF 문서 읽기 (change add-pdf-input).

명세 document-intake "PDF 문서 읽기"의 Scenario. 화면은 frontend/e2e/pdf-input.spec.ts.
같은 내용을 docx(python-docx)와 PDF(reportlab)로 만들어 결과를 비교한다.
"""

from pathlib import Path

from docx import Document
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from rfp_agent.pipeline import dictionaries
from rfp_agent.pipeline.document import process_document
from rfp_agent.pipeline.pdf_reader import read_blocks
from rfp_agent.pipeline.structure import build_tables
from tests.docx_factory import HEADER

VERSION = "test-dict-v1"
SENTENCES = [
    "The switchgear shall comply with IEC 62271-203 and IEC 62271-1.",
    "The maximum ambient temperature for the GIS enclosure shall be 40 °C.",
    "The contractor shall provide spare parts for five years of operation.",
    "All equipment shall be packed for sea transport and long storage.",
    "The vendor shall supply operation and maintenance manuals in English.",
]
ROWS = [
    ["1", "Rated voltage", "kV", "145", ""],
    ["2", "Rated frequency", "Hz", "50", ""],
    ["3", "Rated normal current", "A", "3000", ""],
    ["4", "Rated short-time withstand current, (1 sec.)", "kA", "40", ""],
    ["5", "Annual leakage rate for each gas compartment", "%", "<0.5", ""],
    ["6", "Manufacturer's name", "", "", ""],
]
TITLE = "SCHEDULE OF TECHNICAL DATA"


def table_rows(rows):
    return [["TS-115-GIS"] * len(HEADER), HEADER, *rows]


def build_docx(path: Path, rows=ROWS) -> Path:
    doc = Document()
    doc.add_paragraph(TITLE)
    doc.add_paragraph("1. GENERAL")
    for s in SENTENCES:
        doc.add_paragraph(s)
    doc.add_paragraph("2. DATA SHEET")
    table = doc.add_table(rows=0, cols=len(HEADER))
    for values in table_rows(rows):
        for cell, value in zip(table.add_row().cells, values, strict=True):
            cell.text = value
    doc.save(str(path))
    return path


def footer(c, _doc):
    c.setFont("Helvetica", 8)
    c.drawString(280, 20, f"Page {c.getPageNumber()}")          # 쪽마다 반복되는 꼬리말


def build_pdf(path: Path, rows=ROWS) -> Path:
    style = getSampleStyleSheet()["Normal"]
    story = [Paragraph(TITLE, style), Spacer(1, 12), Paragraph("1. GENERAL", style), Spacer(1, 12)]
    for s in SENTENCES:
        story += [Paragraph(s, style), Spacer(1, 12)]
    story += [Paragraph("2. DATA SHEET", style), Spacer(1, 12)]
    table = Table(table_rows(rows), repeatRows=2)              # 쪽을 넘으면 제목·머리글을 되풀이
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, "black")]))
    story.append(table)
    SimpleDocTemplate(str(path), pagesize=A4).build(story, onFirstPage=footer, onLaterPages=footer)
    return path


def requirements(conn, path):
    result = process_document(conn, path, dictionaries.load(conn), VERSION, None, None)
    rows = conn.execute("SELECT source_kind, text_raw FROM requirement WHERE document_id = %s "
                        "AND req_kind = 'REQUIREMENT' ORDER BY requirement_id",
                        (result.document_id,)).fetchall()
    return result, rows


def test_text_pdf_spec(db, tmp_path):
    """Scenario: 글자가 든 PDF 사양서 — 표 칸·문장 요구사항, 원문 위치, docx와 같은 수."""
    pdf_result, pdf_rows = requirements(db, build_pdf(tmp_path / "gis_spec.pdf"))
    _, docx_rows = requirements(db, build_docx(tmp_path / "gis_spec.docx"))
    assert pdf_result.readable
    kinds = [k for k, _ in pdf_rows]
    assert kinds.count("TABLE_CELL") == len(ROWS) and kinds.count("SENTENCE") == len(SENTENCES)
    assert len(pdf_rows) == len(docx_rows)
    assert any("40 °C" in t for _, t in pdf_rows)
    located = db.execute(
        "SELECT count(*) FROM requirement r JOIN requirement_location rl USING (requirement_id) "
        "JOIN source_location s USING (location_id) WHERE r.document_id = %s "
        "AND s.line_start IS NOT NULL", (pdf_result.document_id,)).fetchone()[0]
    assert located >= len(pdf_rows)                            # 모두 원문 위치(줄 번호)가 있음
    basis = db.execute("SELECT line_basis FROM document WHERE document_id = %s",
                       (pdf_result.document_id,)).fetchone()[0]
    assert basis == "PDF"


def test_table_across_pages(db, tmp_path):
    """Scenario: 쪽을 넘는 표 — 한 표로 이어지고 항목 번호가 이어진다."""
    many = [[str(n), f"Rated value number {n}", "kV", str(100 + n), ""] for n in range(1, 61)]
    path = build_pdf(tmp_path / "long_table.pdf", many)
    blocks = read_blocks(path)
    assert len({b.table_no for b in blocks if b.kind == "R"}) >= 2   # PDF에서는 쪽마다 표가 나뉨
    assert not [b for b in blocks if b.text.startswith("Page ")]    # 쪽마다 반복되는 꼬리말은 뺌
    tables = build_tables(blocks, dictionaries.load(db).column_roles)
    [table] = [t for t in tables if t.name == "TS-115-GIS"]
    numbers = [int(r.item_no) for r in table.rows if r.item_no and r.item_no.isdigit()]
    assert numbers == list(range(1, 61))


def test_pdf_without_text(db, tmp_path):
    """Scenario: 글자가 없는 PDF — 판독 불가, 요구사항 없음."""
    path = tmp_path / "scanned.pdf"
    c = canvas.Canvas(str(path), pagesize=A4)
    c.rect(100, 400, 300, 200, fill=1)                         # 글자 층 없이 그림만
    c.showPage()
    c.save()
    result, rows = requirements(db, path)
    assert result.readable is False and rows == []
