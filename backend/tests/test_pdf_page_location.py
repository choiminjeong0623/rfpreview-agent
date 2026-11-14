"""PDF 원문 위치의 쪽 번호 (change add-pdf-page-location).

명세 document-intake "PDF 원문 위치의 쪽 번호"의 Scenario. 합성 PDF·docx(고객 원문 아님).
"""

from docx import Document
from fastapi.testclient import TestClient
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from rfp_agent.api.main import app
from rfp_agent.pipeline import dictionaries, read_checks
from rfp_agent.pipeline.document import process_document
from rfp_agent.pipeline.pdf_reader import page_of, page_starts, read_blocks
from rfp_agent.pipeline.queries import LOCATIONS
from tests.test_pdf_drawings import BODY, drawing_pdf

VERSION = "test-dict-v1"
W, H = A4
RATED = "The GIS shall have rated current of 3150 A."


def two_page_pdf(path):
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setFont("Helvetica", 10)
    for n, text in enumerate(BODY):
        c.drawString(60, H - 70 - 18 * n, text)
    c.showPage()
    c.setFont("Helvetica", 10)
    c.drawString(60, H - 70, RATED)
    c.showPage()
    c.save()
    return path


def location_of(conn, path, text):
    result = process_document(conn, path, dictionaries.load(conn), VERSION, None, None)
    req = conn.execute("SELECT requirement_id FROM requirement WHERE document_id = %s "
                       "AND text_raw = %s", (result.document_id, text)).fetchone()
    with conn.cursor() as cur:
        cur.execute(LOCATIONS, ([req[0]], None, None))
        cols = [d.name for d in cur.description]
        return dict(zip(cols, cur.fetchone(), strict=True)), result


def test_page_starts():
    """쪽 시작 줄 배열과 줄 → 쪽 (빈 쪽은 다음 쪽, DB 함수와 같은 규칙)"""
    assert page_of([1, 11, 11, 20], 11) == 3
    assert page_of([1, 11, 11, 20], 10) == 1
    assert page_of(None, 5) is None


def test_pdf_requirement_page(db, tmp_path):
    """Scenario: PDF 요구사항의 쪽"""
    path = two_page_pdf(tmp_path / "two.pdf")
    blocks = read_blocks(path)
    assert page_starts(blocks) == [1, len(BODY) + 1]
    loc, result = location_of(db, path, RATED)
    assert loc["page"] == 2
    starts = db.execute("SELECT page_starts FROM document WHERE document_id = %s",
                        (result.document_id,)).fetchone()[0]
    assert starts == [1, len(BODY) + 1]


def test_docx_has_no_page(db, tmp_path):
    """Scenario: docx 위치에는 쪽 없음"""
    doc = Document()
    for text in [*BODY, RATED]:
        doc.add_paragraph(text)
    doc.save(str(tmp_path / "same.docx"))
    loc, _ = location_of(db, tmp_path / "same.docx", RATED)
    assert loc["page"] is None


def test_drawing_check_page(db, tmp_path):
    """Scenario: 도면 쪽 점검 줄의 쪽"""
    result = process_document(db, drawing_pdf(tmp_path / "drawing.pdf"), dictionaries.load(db),
                              VERSION, None, None)
    run_id = db.execute("INSERT INTO review_run (started_by, stage, dict_version) "
                        "VALUES (1, 'ENGINEER_REVIEW', 't') RETURNING run_id").fetchone()[0]
    db.execute("INSERT INTO run_document (run_id, document_id) VALUES (%s, %s)",
               (run_id, result.document_id))
    rows = read_checks.read_checks(db, run_id)
    figure = next(r for r in rows if r["kind"] == "그림")
    assert figure["loc"].startswith("2쪽 · 도면 DWG-SLD-001")


def test_api_location_page():
    """응답 모양에 쪽 칸이 있다 (없을 수 있음)"""
    spec = TestClient(app).get("/openapi.json").json()
    assert "page" in spec["components"]["schemas"]["Location"]["properties"]
