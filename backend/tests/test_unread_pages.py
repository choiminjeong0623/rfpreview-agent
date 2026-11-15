"""읽지 못한 쪽 알림 (change add-unread-pages, FR-19·CR-13·AR-09).

명세 document-intake "쪽마다 읽은 결과 기록"·"그림의 OCR 이유"·"읽지 못한 쪽 등록 안내와 거절 이유",
review-workspace "문서 읽기 점검의 쪽 줄"·"문서 표의 읽은 쪽", review-approval "읽지 못한 쪽 확인
기준 (AR-09)"의 Scenario. OCR 결과는 대역으로 바꿔 Tesseract 없이도 같은 결과가 나오게 한다.
"""

import io
import json
from pathlib import Path

import pytest
from docx import Document
from docx.shared import Inches
from PIL import Image, ImageDraw
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from rfp_agent.pipeline import ocr, pdf_reader, queries, read_checks, review
from rfp_agent.pipeline.run import RunContext, create_run, execute_run

VERSION = "test-dict-v1"
# 글자 쪽 하나만으로도 판독 가능(10줄 이상)하게 줄을 채운다
FILLER = [f"1.{n} Item {n} shall be supplied with the documents listed in the schedule."
          for n in range(1, 9)]
TEXT_PAGES = {
    1: ["1. GENERAL", "The switchgear shall be rated 145 kV."] + FILLER,
    3: ["3. TESTS", "All panels shall be tested at the factory."] + FILLER,
}


def scan_image() -> Image.Image:
    """스캔한 쪽처럼 보이는 그림 (실제 글자는 대역 OCR이 정한다)."""
    image = Image.new("RGB", (1200, 900), "white")
    draw = ImageDraw.Draw(image)
    for n in range(8):
        draw.line((60, 80 + 90 * n, 1100, 90 + 90 * n), fill="gray", width=6)
    return image


def build_pdf(path: Path, pages: list[str]) -> Path:
    """pages: 쪽마다 "text"(글자 쪽) / "scan"(그림만) / "blank"(아무것도 없음)."""
    c = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4
    for no, kind in enumerate(pages, start=1):
        if kind == "text":
            y = height - 80
            for line in TEXT_PAGES.get(no, TEXT_PAGES[1]):
                c.drawString(60, y, line)
                y -= 24
        elif kind == "scan":
            c.drawImage(ImageReader(scan_image()), 40, 120, width - 80, (width - 80) * 0.75)
        c.showPage()
    c.save()
    return path


@pytest.fixture
def low_conf(monkeypatch):
    """OCR은 켜져 있지만 모든 줄이 신뢰도 기준 미만 (3줄 버림, 평균 41)."""
    monkeypatch.setattr(ocr, "available", lambda: True)
    monkeypatch.setattr(ocr, "unavailable_reason", lambda: None)
    monkeypatch.setattr(ocr, "read", lambda image: ocr.OcrResult([], 3, 41.0))


@pytest.fixture
def ocr_off(monkeypatch):
    monkeypatch.setattr(ocr, "available", lambda: False)
    monkeypatch.setattr(ocr, "unavailable_reason", lambda: ocr.OCR_OFF)


def run_once(conn, paths: list[Path]) -> int:
    run_id = create_run(conn, VERSION, None)
    choices = {p.name: {"bundle": "B"} for p in paths}
    assert execute_run(RunContext(conn, VERSION, None, None), run_id, paths, choices) \
        == "ENGINEER_REVIEW"
    return run_id


def document_of(conn, run_id: int) -> dict:
    [doc] = queries.run_documents(conn, run_id)
    unread = conn.execute("SELECT unread_pages FROM document WHERE document_id = %s",
                          (doc["document_id"],)).fetchone()[0]
    return doc | {"unread_pages": unread}


def requirements(conn, run_id: int) -> list[str]:
    return [r[0] for r in conn.execute(
        "SELECT q.text_raw FROM requirement q JOIN run_document USING (document_id) "
        "WHERE run_id = %s AND q.req_kind = 'REQUIREMENT'", (run_id,))]


def page_rows(conn, run_id: int) -> list[dict]:
    return [r for r in read_checks.read_checks(conn, run_id) if r["kind"] == "쪽"]


# ── document-intake ───────────────────────────────────────────────────

def test_scan_page_between_text_pages(db, tmp_path, low_conf):
    """Scenario: 스캔 쪽 하나가 낀 PDF — 1·3쪽 요구사항, 3쪽 중 2쪽 읽음, 2쪽 OCR 신뢰도 낮음."""
    run = run_once(db, [build_pdf(tmp_path / "scan_mid.pdf", ["text", "scan", "text"])])
    texts = requirements(db, run)
    assert any("145 kV" in t for t in texts) and any("tested at the factory" in t for t in texts)
    doc = document_of(db, run)
    assert (doc["page_count"], doc["pages_read"], doc["pages_blank"]) == (3, 2, 0)
    assert doc["unread_pages"] == [{"page": 2, "reason": "OCR_LOW_CONF", "dropped": 3,
                                    "dropped_conf": 41.0}]


def test_scan_pages_with_ocr_off(tmp_path, ocr_off):
    """Scenario: OCR을 끈 스캔 쪽 — 읽지 못한 쪽 2개, 이유 OCR 꺼짐."""
    _, scan = pdf_reader.read_pdf(build_pdf(tmp_path / "two.pdf", ["text", "scan", "scan"]))
    assert [(u["page"], u["reason"]) for u in scan.unread] == [(2, "OCR_OFF"), (3, "OCR_OFF")]


def test_blank_page(tmp_path, ocr_off):
    """Scenario: 빈 쪽 — 빈 쪽 수 1, 읽지 못한 쪽 목록에 없음."""
    _, scan = pdf_reader.read_pdf(build_pdf(tmp_path / "blank.pdf", ["text", "blank", "text"]))
    assert (scan.page_count, scan.pages_read, scan.pages_blank, scan.unread) == (3, 2, 1, [])


def test_same_file_twice(tmp_path, low_conf):
    """Scenario: 같은 파일을 두 번 분석 — 읽지 못한 쪽 목록이 같다."""
    path = build_pdf(tmp_path / "again.pdf", ["scan", "text", "scan", "blank"])
    first, second = pdf_reader.read_pdf(path)[1], pdf_reader.read_pdf(path)[1]
    assert first.unread == second.unread and [u["page"] for u in first.unread] == [1, 3]


def test_half_unread_needs_review(db, tmp_path, low_conf):
    """Scenario: 절반 이상 읽지 못한 문서 — 확인 필요."""
    run = run_once(db, [build_pdf(tmp_path / "mostly_scan.pdf", ["text", "scan", "scan"])])
    doc = document_of(db, run)
    assert doc["needs_review"] and len(doc["unread_pages"]) == 2


def docx_with_picture(path: Path) -> Path:
    doc = Document()
    doc.add_paragraph("TECHNICAL SPECIFICATION")
    for n in range(10):
        doc.add_paragraph(f"Clause {n + 1}: the contractor shall keep the records listed here.")
    buf = io.BytesIO()
    scan_image().save(buf, format="PNG")
    buf.seek(0)
    doc.add_picture(buf, width=Inches(5))
    doc.add_paragraph("Fig. 1 Layout")
    doc.save(str(path))
    return path


def test_docx_figure_reason_ocr_off(db, tmp_path, ocr_off):
    """Scenario: OCR을 끈 docx 그림 — 그림 위치에 이유 OCR 꺼짐."""
    run = run_once(db, [docx_with_picture(tmp_path / "picture.docx")])
    figures = db.execute(
        "SELECT f.caption, f.ocr_reason FROM doc_figure f JOIN run_document USING (document_id) "
        "WHERE run_id = %s", (run,)).fetchall()
    assert figures == [("Fig. 1 Layout", "OCR_OFF")]
    [row] = [r for r in read_checks.read_checks(db, run) if r["kind"] == "그림"]
    assert row["problem"].startswith("OCR이 꺼져 있어 그림 속 글자를 읽지 않았습니다.")
    assert document_of(db, run)["page_count"] is None                    # docx는 쪽 없음


@pytest.fixture
def client(db, db_url, monkeypatch):
    from fastapi.testclient import TestClient

    from rfp_agent.api.main import app
    from rfp_agent.config import get_settings

    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    get_settings.cache_clear()
    yield TestClient(app)
    get_settings.cache_clear()


def test_preview_with_ocr_off(client, tmp_path, ocr_off):
    """Scenario: OCR이 꺼진 등록 미리 보기 — 읽지 못한 쪽 2, 이유 OCR 꺼짐."""
    path = build_pdf(tmp_path / "two_scans.pdf", ["text", "scan", "scan"])
    res = client.post("/api/runs/preview", files=[("files", (path.name, path.read_bytes()))])
    assert res.status_code == 200, res.text
    [p] = res.json()
    assert (p["page_count"], p["unread_pages"], p["unread_reason"]) == (3, 2, "OCR_OFF")


def test_reject_when_judged_file_unread(client, db, tmp_path, low_conf):
    """Scenario: 판정할 문서를 모두 읽지 못한 등록 — 검토를 만들지 않고 이유와 함께 거절."""
    path = build_pdf(tmp_path / "all_scan.pdf", ["scan", "scan"])
    # 등록 화면은 먼저 미리 보기를 부른다. 등록 검사는 그 결과를 다시 쓴다 (add-run-queue, NFR-11)
    assert client.post("/api/runs/preview",
                       files=[("files", (path.name, path.read_bytes()))]).status_code == 200
    data = {"choices": json.dumps({path.name: {"bundle": "A"}}), "due_date": "2026-12-01"}
    res = client.post("/api/runs", files=[("files", (path.name, path.read_bytes()))], data=data)
    assert res.status_code == 400
    assert res.json()["detail"].startswith("판정할 문서를 읽지 못했습니다(모든 쪽 OCR 실패)")
    assert db.execute("SELECT count(*) FROM review_run").fetchone()[0] == 0


# ── review-workspace ──────────────────────────────────────────────────

def test_read_check_page_row(db, tmp_path, low_conf):
    """Scenario: 스캔 쪽 하나의 점검 줄 — "쪽" 줄 1개, 위치 "2쪽", 신뢰도가 낮아 읽지 못함."""
    run = run_once(db, [build_pdf(tmp_path / "scan_mid.pdf", ["text", "scan", "text"])])
    rows = read_checks.read_checks(db, run)
    [row] = page_rows(db, run)
    assert rows[0] is row or rows[0]["kind"] == "쪽"                          # 쪽 줄이 먼저
    assert row["loc"] == "2쪽" and row["what"] == "스캔 쪽 · OCR 신뢰도가 낮아 읽지 못함"
    assert "3줄" in row["problem"] and row["todo"] == "원문을 직접 확인"


def test_read_check_ocr_off_rows(db, tmp_path, ocr_off):
    """Scenario: OCR을 끈 스캔 쪽 점검 줄 — 이유가 OCR 꺼짐인 "쪽" 줄 2개."""
    run = run_once(db, [build_pdf(tmp_path / "two.pdf", ["text", "scan", "scan"])])
    rows = page_rows(db, run)
    assert [r["loc"] for r in rows] == ["2쪽", "3쪽"]
    assert all(r["what"] == "스캔 쪽 · OCR이 꺼져 있음" for r in rows)


def test_blank_page_has_no_row(db, tmp_path, ocr_off):
    """Scenario: 빈 쪽은 점검 줄 없음."""
    run = run_once(db, [build_pdf(tmp_path / "blank.pdf", ["text", "blank", "text"])])
    assert page_rows(db, run) == []
    assert document_of(db, run)["pages_blank"] == 1


def test_document_table_pages_read(db, tmp_path, low_conf):
    """Scenario: 스캔 쪽이 낀 PDF의 읽은 쪽 — 문서 표 응답에 2 / 3."""
    from rfp_agent.api.schemas import RunDocument

    run = run_once(db, [build_pdf(tmp_path / "scan_mid.pdf", ["text", "scan", "text"])])
    [doc] = queries.run_documents(db, run)
    shown = RunDocument.model_validate(doc)
    assert (shown.pages_read, shown.page_count) == (2, 3)


# ── review-approval ───────────────────────────────────────────────────

def test_ar09_unchecked_page(db, tmp_path, low_conf):
    """Scenario: 확인하지 않은 쪽 줄 — 상신 전 확인에 AR-09."""
    run = run_once(db, [build_pdf(tmp_path / "scan_mid.pdf", ["text", "scan", "text"])])
    [ar09] = [c for c in review.criteria(db, run) if c.ar_code == "AR-09"]
    assert ar09.detail == "읽지 못한 쪽 1개 미확인"


def test_ar09_cleared_after_check(db, tmp_path, low_conf):
    """Scenario: 쪽 줄을 확인한 뒤 — AR-09가 걸리지 않고 이력에 확인 1건."""
    run = run_once(db, [build_pdf(tmp_path / "scan_mid.pdf", ["text", "scan", "text"])])
    [row] = page_rows(db, run)
    read_checks.set_checked(db, run, row["key"], True)
    assert "AR-09" not in [c.ar_code for c in review.criteria(db, run)]
    assert len(review.history(db, run, target="read_check")) == 1
