"""일탈 목록·질의서 초안 Word 파일 (SCR-08-11, 목업 "일탈 목록 초안.docx").

목록 항목(run_outputs)을 그대로 옮긴다. 뺀 항목은 넣지 않고, 원문 위치가 없는 항목은 run_outputs가
이미 내지 않는다(CR-02). 문장은 고치지 않고 후보·팀 가정·숫자 확인 표시만 붙인다(CR-06·07·08).
"""

from io import BytesIO

import psycopg
from docx import Document

from rfp_agent.pipeline import queries

TITLES = {"DEVIATION": "일탈 목록 초안", "QUERY": "질의서 초안"}
STATUS = {"CANDIDATE": "후보", "CONFIRMED": "확정", "EDITED": "수정함"}
HEADER = ["No.", "원문 위치", "문장", "상태"]


def location_text(loc: dict, names: dict[int, str]) -> str:
    """화면과 같은 원문 위치 형식: 파일 이름 · 표 n번 또는 절 · n행 (_공통규칙.md 3장)."""
    if loc["table_name"]:
        where = loc["table_name"] + (f" {loc['item_no']}번" if loc["item_no"] else "")
    else:
        where = f"{loc['section_no'] or ''} {loc['section_title'] or ''}".strip()
    parts = [names.get(loc["file_no"], f"파일 {loc['file_no']}"),
             f"{loc['page']}쪽" if loc.get("page") else "", where,     # PDF 쪽
             f"{loc['line_start']}행" if loc["line_start"] else ""]
    return " · ".join(p for p in parts if p)


def outputs_docx(conn: psycopg.Connection, run_id: int, list_kind: str) -> tuple[str, bytes]:
    """(파일 이름, Word 바이트)."""
    run = queries.run_summary(conn, run_id)
    names = {d["file_no"]: d["file_name"] for d in queries.run_documents(conn, run_id)}
    items = [i for i in queries.run_outputs(conn, run_id, list_kind) if i["status"] != "REMOVED"]
    title = TITLES[list_kind]
    doc = Document()
    doc.add_heading(title, level=1)
    name = " · ".join(x for x in (run.get("project_name"), run.get("review_name")) if x)
    doc.add_paragraph(f"{run['review_no']}" + (f" · {name}" if name else ""))
    doc.add_paragraph("모든 문장은 후보입니다. 확정은 담당 엔지니어가 합니다. "
                      "\"팀 가정\"은 팀이 정한 값이 들어간 문장입니다.")
    if items and items[0]["list_name"]:
        doc.add_paragraph(f"목록 이름: {items[0]['list_name']}")
    table = doc.add_table(rows=1, cols=len(HEADER))
    table.style = "Table Grid"
    for cell, text in zip(table.rows[0].cells, HEADER, strict=True):
        cell.text = text
    for n, item in enumerate(items, start=1):
        marks = [STATUS.get(item["status"], item["status"])]
        if item["is_assumed"]:
            marks.append("팀 가정")
        if item["number_check"] == "MISMATCH":
            marks.append("숫자 확인 필요")
        cells = table.add_row().cells
        cells[0].text = str(n)
        cells[1].text = "\n".join(location_text(loc, names) for loc in item["locations"])
        cells[2].text = item["text_draft"]
        cells[3].text = " · ".join(marks)
    if not items:
        doc.add_paragraph("목록에 올릴 항목이 없습니다.")
    out = BytesIO()
    doc.save(out)
    return f"{title}_{run['review_no']}.docx", out.getvalue()
