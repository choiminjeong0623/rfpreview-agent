"""데이터시트 채우기 (SCR-10, 목업 Datasheet). 화면과 엑셀이 같은 줄을 쓴다 (CR-11).

고객 표(doc_table) 하나의 현재 판정 줄을 원문 행 순서대로 옮긴다. 요구값이 빈 칸(보증값 작성)은
보증값 후보, 나머지는 판정의 제품값을 채운 값으로 쓴다. 근거 값이 없으면 비워 두고
"확인 필요"로 둔다(CR-04).
"""

from io import BytesIO

import psycopg
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from psycopg.rows import dict_row

from rfp_agent.pipeline import queries
from rfp_agent.pipeline.compare import REASONS
from rfp_agent.pipeline.tbe import with_unit

STATE = {"ok": "확정", "cand": "후보", "empty": "확인 필요"}
RESULT_NAMES = {"DEVIATION_CANDIDATE": "일탈 후보", "QUERY_CANDIDATE": "질의 후보",
                "NEEDS_REVIEW": "확인 필요"}
# 보증값 후보가 비는 이유 (warranty._empty)
EMPTY_REASONS = REASONS | {
    "NOT_MAPPED": "연결표에 없는 항목 · 담당 확인",
    "NO_FIXED_VALUE": "회사 고정값 없음",
    "NO_PRODUCT_VALUE": "제품표에 값이 없음 · 설계 담당 확인",
}
HEADER = ["칸", "Item", "항목", "Unit", "Requirement", "Offered", "Basis", "Status"]

ROWS = """
    SELECT j.judgment_id, j.result, j.review_status, j.product_code, j.product_value_raw,
           j.product_value_unit, j.reason_code, j.is_assumed, v.raw_text AS req_value_raw,
           v.unit_raw, v.item_key, k.name_ko AS item_name, tr.item_name_raw, tr.item_no,
           tr.unit_raw AS row_unit, w.candidate_id, w.candidate_value, w.candidate_unit,
           w.source_kind, w.product_code AS w_product, w.pm_column, w.status AS w_status,
           w.reason_code AS w_reason, w.is_assumed AS w_assumed
    FROM judgment j
    JOIN req_value v ON v.value_id = j.value_id
    JOIN requirement q ON q.requirement_id = j.requirement_id
    JOIN table_row tr ON tr.row_id = q.row_id
    LEFT JOIN item_key k ON k.item_key = v.item_key
    LEFT JOIN warranty_candidate w ON w.judgment_id = j.judgment_id
    WHERE j.run_id = %(run)s AND j.is_current AND j.review_status <> 'REJECTED'
      AND tr.table_id = %(table)s
    ORDER BY tr.row_order, tr.row_id, v.value_seq, j.judgment_id"""


class NotFound(LookupError):
    pass


def datasheets(conn: psycopg.Connection, run_id: int) -> list[dict]:
    """판정이 있는 고객 표마다 칸 수와 빈 칸 수 (파일 번호 → 표 순서)."""
    with conn.cursor(row_factory=dict_row) as cur:
        tables = cur.execute(
            """SELECT DISTINCT t.table_id, t.table_name, d.file_no, d.file_name
               FROM judgment j JOIN requirement q ON q.requirement_id = j.requirement_id
               JOIN table_row tr ON tr.row_id = q.row_id
               JOIN doc_table t ON t.table_id = tr.table_id
               JOIN document d ON d.document_id = t.document_id
               WHERE j.run_id = %s AND j.is_current AND j.review_status <> 'REJECTED'
               ORDER BY d.file_no, t.table_id""", (run_id,)).fetchall()
    out = []
    for t in tables:
        rows = _rows(conn, run_id, t["table_id"])
        name = t["table_name"] or f"표 {t['table_id']}"
        out.append({"table_id": t["table_id"], "table_name": name,
                    "file_name": t["file_name"], "rows": len(rows),
                    "empty": sum(1 for r in rows if r["state"] == "empty")})
    return out


def _basis(r: dict) -> str:
    if r["source_kind"] == "FIXED":
        return "회사 고정값"
    if r["source_kind"] == "ENGINEER":
        return "직접 입력"
    if r["source_kind"]:
        return " ".join(x for x in ("제품표", r["w_product"], r["pm_column"]) if x)
    return ""


def _line(r: dict) -> dict:
    """한 줄의 채운 값·근거·상태. 보증값 작성은 보증값 후보, 그 밖은 판정 제품값."""
    if r["result"] == "WARRANTY_TO_FILL":
        value = with_unit(r["candidate_value"], r["candidate_unit"])
        if r["candidate_id"] is None or not value or r["w_status"] == "REJECTED":
            state, why = "empty", EMPTY_REASONS.get(r["w_reason"] or "", "근거 값 없음")
        else:
            state, why = ("ok" if r["w_status"] == "CONFIRMED" else "cand"), ""
        basis, assumed, target = _basis(r) if value else "", bool(r["w_assumed"]), "warranty"
    else:
        value = with_unit(r["product_value_raw"], r["product_value_unit"])
        if value and r["product_code"]:
            value += f" ({r['product_code']})"
        if not value:
            state, why = "empty", REASONS.get(r["reason_code"] or "", "제품값 없음")
        else:
            confirmed = r["review_status"] in ("CONFIRMED", "EDITED")
            state, why = ("ok" if confirmed else "cand"), ""
        basis = " · ".join(x for x in (
            f"제품표 {r['product_code']}" if value and r["product_code"] else "",
            f"판정 {RESULT_NAMES[r['result']]}" if r["result"] in RESULT_NAMES else "") if x)
        assumed, target = bool(r["is_assumed"]), "judgment"
    if assumed and value:
        basis = f"{basis} · 팀 가정" if basis else "팀 가정"
    return {
        "judgment_id": r["judgment_id"], "candidate_id": r["candidate_id"], "target": target,
        "no": (r["item_no"] or "").strip() or "—",
        "item": r["item_name"] or r["item_name_raw"] or "",
        "item_en": r["item_name_raw"] or "", "unit": r["unit_raw"] or r["row_unit"] or "",
        "requirement": r["req_value_raw"] or "—", "value": value or None, "basis": basis,
        "why": why, "state": state, "status": STATE[state], "assumed": assumed,
    }


def _rows(conn: psycopg.Connection, run_id: int, table_id: int) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(ROWS, {"run": run_id, "table": table_id}).fetchall()
    return [_line(r) for r in rows]


def datasheet(conn: psycopg.Connection, run_id: int, table_id: int) -> dict:
    """{file_name, table_name, source_file, rows, counts}."""
    sheets = {s["table_id"]: s for s in datasheets(conn, run_id)}
    if table_id not in sheets:
        raise NotFound(f"이 검토에 데이터시트(표 {table_id})가 없습니다.")
    sheet = sheets[table_id]
    run = queries.run_summary(conn, run_id)
    rows = _rows(conn, run_id, table_id)
    n = {k: sum(1 for r in rows if r["state"] == k) for k in STATE}
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in sheet["table_name"])
    return {
        "file_name": f"Datasheet_{safe}_{run['review_no']}.xlsx", "review_no": run["review_no"],
        "table_id": table_id, "table_name": sheet["table_name"], "source_file": sheet["file_name"],
        "rows": rows, "counts": {"rows": len(rows), "ok": n["ok"], "cand": n["cand"],
                                 "empty": n["empty"]},
    }


def datasheet_xlsx(conn: psycopg.Connection, run_id: int,
                   table_id: int) -> tuple[str, bytes, int]:
    """(파일 이름, 엑셀 바이트, 줄 수). 칸 순서는 화면과 같다."""
    data = datasheet(conn, run_id, table_id)
    wb = Workbook()
    ws = wb.active
    ws.title = "Datasheet"
    ws.append([f"{data['table_name']} · {data['source_file']} · {data['review_no']}"])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append(["채운 값은 후보입니다. \"확인 필요\" 칸은 근거 값이 없어 비워 두었습니다. "
               "팀 가정 값은 근거에 표시했습니다."])
    ws.append([])
    ws.append(HEADER)
    head = ws.max_row
    for cell in ws[head]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="EEF2F6")
    for r in data["rows"]:
        why = r["why"] and f" ({r['why']})"
        ws.append([r["no"], r["item_en"], r["item"], r["unit"], r["requirement"], r["value"] or "",
                   r["basis"], r["status"] + (why if r["state"] == "empty" else "")])
    for col, width in zip("ABCDEFGH", (8, 40, 24, 10, 18, 26, 30, 30), strict=True):
        ws.column_dimensions[col].width = width
    for row in ws.iter_rows(min_row=head + 1):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = ws.cell(row=head + 1, column=1)
    out = BytesIO()
    wb.save(out)
    return data["file_name"], out.getvalue(), len(data["rows"])
