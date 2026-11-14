"""PDF 단락 잇기와 선 없는 공급사 답안 표 (change update-pdf-tables).

명세 document-intake "PDF 단락 잇기"·"공급사 답안 PDF의 표 행"의 Scenario.
실제 RFP를 PDF로 바꿨을 때의 모양을 reportlab으로 글자 위치를 정해 그린다(고객 원문 아님).
"""

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from rfp_agent.pipeline import dictionaries
from rfp_agent.pipeline.document import process_document
from rfp_agent.pipeline.pdf_reader import read_blocks

VERSION = "test-dict-v1"
FILLER = [f"Clause {n + 1}: the contractor shall keep the records listed in this section."
          for n in range(8)]
WRAP_1 = "2) All circuit breakers shall be provided with anti-condensation"
WRAP_2 = "heaters controlled by a thermostat in each operating cabinet."
WRAPPED = f"{WRAP_1} {WRAP_2}"


def draw(path: Path, lines: list[tuple[float, float, str]]) -> Path:
    """(x, 위에서부터 y, 글) 줄을 한 쪽에 그린다. 글자 크기 10."""
    c = canvas.Canvas(str(path), pagesize=A4)
    _, height = A4
    c.setFont("Helvetica", 10)
    for x, y, text in lines:
        c.drawString(x, height - y, text)
    c.save()
    return path


def stacked(texts: list[str], top: float, pitch: float) -> list[tuple[float, float, str]]:
    return [(72, top + n * pitch, t) for n, t in enumerate(texts)]


def processed(db, path):
    result = process_document(db, path, dictionaries.load(db), VERSION, None, None)
    reqs = db.execute("SELECT text_raw, supplier_mark FROM requirement WHERE document_id = %s "
                      "AND req_kind = 'REQUIREMENT'", (result.document_id,)).fetchall()
    kind = db.execute("SELECT doc_kind FROM document WHERE document_id = %s",
                      (result.document_id,)).fetchone()[0]
    titles = [t for (t,) in db.execute("SELECT title FROM section WHERE document_id = %s",
                                       (result.document_id,))]
    return reqs, kind, titles


def test_wrapped_numbered_paragraph(db, tmp_path):
    """Scenario: 번호로 시작하는 접힌 단락 — 한 줄로 이은 요구사항 하나, 첫 줄은 제목 아님."""
    lines = stacked(["TECHNICAL SPECIFICATION", "1. GENERAL"], 72, 24)
    lines += stacked([WRAP_1, WRAP_2], 130, 12)                 # 단락 안 줄 간격 2pt
    lines += stacked(FILLER, 170, 24)
    reqs, _, titles = processed(db, draw(tmp_path / "wrap.pdf", lines))
    assert WRAPPED in [t for t, _ in reqs]
    assert not any(t.startswith("All circuit breakers") for t in titles)


def test_wide_line_spacing(db, tmp_path):
    """Scenario: 줄 간격이 넓은 문서 — 단락 안 간격이 넓어도 접힌 문장이 한 단락."""
    lines, y = [], 72.0
    for n in range(6):
        first = f"{n + 1}) The contractor shall submit the design documents for item {n + 1}"
        lines += [(72, y, first), (72, y + 19, "before the start of the manufacturing work.")]
        y += 19 + 26                                          # 단락 안 9pt, 단락 사이 16pt
    texts = [b.text for b in read_blocks(draw(tmp_path / "wide.pdf", lines)) if b.kind == "P"]
    assert texts[0] == ("1) The contractor shall submit the design documents for item 1 "
                        "before the start of the manufacturing work.")
    assert len(texts) == 6


def test_even_line_spacing(db, tmp_path):
    """Scenario: 간격이 고른 문서 — 한 줄짜리 shall 문장 다섯이 각각 요구사항."""
    sentences = [f"The vendor shall supply item {n + 1} with the type test report."
                 for n in range(5)]
    lines = stacked(["TECHNICAL SPECIFICATION", "1. GENERAL"], 72, 24)
    lines += stacked(sentences, 130, 24) + stacked(FILLER, 260, 24)
    reqs, _, _ = processed(db, draw(tmp_path / "even.pdf", lines))
    assert all(s in [t for t, _ in reqs] for s in sentences)


def supplier_lines() -> list[tuple[float, float, str]]:
    lines = [(263, 86, "SECTION 26 2000"), (428, 94, "C:"),
             (236, 106, "ELECTRIC DISTRIBUTION"), (428, 108, "Complied"),
             (428, 122, "D: Deviation"), (259, 136, "PART 1 - GENERAL"),
             (428, 136, "E:"), (428, 150, "Exclusion"),
             (72, 180, "1.3"), (108, 180, "SUBMITTALS"),
             (86, 199, "C"), (144, 205, "1. Manufacturer and equipment type."),
             (86, 225, "E"), (144, 231, "2. Wiring diagrams by the installing contractor."),
             (108, 255, "A. Submit the following product data and information:")]
    return lines + stacked(FILLER, 300, 24)


def test_supplier_answer_pdf(db, tmp_path):
    """Scenario: 선 없는 공급사 답안 PDF — 공급사 사양서, 표시 C 조항, 절 제목은 그대로."""
    reqs, kind, titles = processed(db, draw(tmp_path / "answer.pdf", supplier_lines()))
    assert kind == "SUPPLIER_SPEC"
    marks = {t: m for t, m in reqs}
    assert marks["1. Manufacturer and equipment type."] == "C"
    assert marks["2. Wiring diagrams by the installing contractor."] == "E"
    assert "A. Submit the following product data and information:" in marks
    assert "SUBMITTALS" in titles


def test_no_legend_no_rows(db, tmp_path):
    """Scenario: 준수 표시 머리가 없는 PDF — "C" 한 글자 줄이 있어도 표 행을 만들지 않음."""
    lines = [ln for ln in supplier_lines() if ln[2] not in ("C:", "Complied")]
    assert not [b for b in read_blocks(draw(tmp_path / "plain.pdf", lines)) if b.kind == "R"]
