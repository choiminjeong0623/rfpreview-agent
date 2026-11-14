"""OCR — 스캔 PDF와 그림 속 글자 읽기 (change add-ocr).

명세 document-intake "OCR로 글자 읽기"·service-health "OCR 사용 가능 표시"의 Scenario.
흰 바탕에 큰 글씨 문장을 그린 그림으로 스캔 PDF·그림 든 docx를 만든다. Tesseract가 있어야 한다.
"""

import io
from pathlib import Path

import pytest
from docx import Document
from docx.shared import Inches
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from rfp_agent.api.main import app
from rfp_agent.pipeline import dictionaries, ocr
from rfp_agent.pipeline.document import process_document

pytestmark = pytest.mark.skipif(ocr.engine_version() is None, reason="Tesseract 없음")

VERSION = "test-dict-v1"
RATED = "The switchgear shall be rated 145 kV."
SCANNED = [
    RATED,
    "The enclosure shall be painted light grey.",
    "The contractor shall provide spare parts.",
    "All panels shall be tested at the factory.",
    "The vendor shall supply the manuals.",
    "Cables shall be routed in closed trays.",
    "Each bay shall have a local control panel.",
    "The earthing switch shall be motor operated.",
    "Drawings shall be approved before work.",
    "The bidder shall state the delivery time.",
]
PAINT = "The enclosure shall be painted RAL 7032."


def picture(lines: list[str]) -> Image.Image:
    """흰 바탕에 줄마다 큰 글씨 (줄 사이를 띄워 줄마다 단락이 된다)."""
    font = ImageFont.load_default(size=44)
    image = Image.new("RGB", (2000, 140 * len(lines) + 100), "white")
    draw = ImageDraw.Draw(image)
    for n, line in enumerate(lines):
        draw.text((60, 60 + 140 * n), line, fill="black", font=font)
    return image


def scanned_pdf(path: Path) -> Path:
    image = picture(SCANNED)
    c = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4
    c.drawImage(ImageReader(image), 20, 20, width - 40, (width - 40) * image.height / image.width)
    c.showPage()
    c.save()
    return path


def docx_with_picture(path: Path) -> Path:
    doc = Document()
    doc.add_paragraph("TECHNICAL SPECIFICATION")
    for n in range(10):
        doc.add_paragraph(f"Clause {n + 1}: the contractor shall keep the records listed here.")
    buf = io.BytesIO()
    picture([PAINT]).save(buf, format="PNG")
    buf.seek(0)
    doc.add_picture(buf, width=Inches(6))
    doc.add_paragraph("Fig. 1 Painting requirement")
    doc.save(str(path))
    return path


def processed(conn, path):
    result = process_document(conn, path, dictionaries.load(conn), VERSION, None, None)
    reqs = conn.execute("SELECT text_raw, extracted_by, confidence FROM requirement "
                        "WHERE document_id = %s AND req_kind = 'REQUIREMENT'",
                        (result.document_id,)).fetchall()
    doc = conn.execute("SELECT readable, needs_review, ocr_lines FROM document "
                       "WHERE document_id = %s", (result.document_id,)).fetchone()
    return result, reqs, doc


def test_scanned_pdf(db, tmp_path):
    """Scenario: 스캔한 PDF 사양서 — 판독 가능, OCR 요구사항과 원문 위치, 확인 필요."""
    result, reqs, (readable, review, ocr_lines) = processed(db, scanned_pdf(tmp_path / "scan.pdf"))
    assert readable and review and ocr_lines >= len(SCANNED)
    [rated] = [r for r in reqs if "145 kV" in r[0]]
    assert rated[1:] == ("OCR", 0.5)
    located = db.execute(
        "SELECT s.line_start FROM requirement r JOIN requirement_location USING (requirement_id) "
        "JOIN source_location s USING (location_id) WHERE r.document_id = %s AND r.text_raw = %s",
        (result.document_id, rated[0])).fetchone()
    assert located and located[0] >= 1


def test_docx_picture_text(db, tmp_path):
    """Scenario: docx 그림 속 문장 — 그림 위치가 남고 그 문장이 OCR 요구사항."""
    result, reqs, (_, review, ocr_lines) = processed(db, docx_with_picture(tmp_path / "spec.docx"))
    [paint] = [r for r in reqs if "RAL 7032" in r[0]]
    assert paint[1] == "OCR" and review and ocr_lines >= 1
    figures = db.execute("SELECT caption FROM doc_figure WHERE document_id = %s",
                         (result.document_id,)).fetchall()
    assert figures == [("Fig. 1 Painting requirement",)]
    assert all(r[1] == "RULE" for r in reqs if r[0].startswith("Clause"))   # 글자 층은 그대로


def test_ocr_off(db, tmp_path, monkeypatch):
    """Scenario: OCR 엔진 없음 — 스캔 PDF는 판독 불가, 요구사항 없음."""
    monkeypatch.setattr(ocr, "available", lambda: False)
    _, reqs, (readable, _, ocr_lines) = processed(db, scanned_pdf(tmp_path / "scan.pdf"))
    assert (readable, reqs, ocr_lines) == (False, [], 0)


def test_health_ocr(monkeypatch):
    """Scenario: OCR 상태 — 켜면 true와 엔진 판, 끄면 false."""
    client = TestClient(app)
    body = client.get("/api/health").json()
    assert body["ocr_available"] is True and body["ocr_engine"] == ocr.engine_version()
    monkeypatch.setattr(ocr, "available", lambda: False)
    body = client.get("/api/health").json()
    assert (body["ocr_available"], body["ocr_engine"]) == (False, None)

def test_api_allows_ocr_requirement():
    """OCR로 뽑은 요구사항(extracted_by = OCR)도 API 응답 모양에 맞는다.

    11-03 RFP08 문서에서 응답 오류가 났던 경우.
    """
    from typing import get_args

    from rfp_agent.api.schemas import Requirement
    assert "OCR" in get_args(Requirement.model_fields["extracted_by"].annotation)
