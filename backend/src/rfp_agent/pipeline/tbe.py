"""TBE 준수표 (SCR-09, 목업 Tbe). 미리보기와 엑셀이 같은 줄을 쓴다 (CR-11).

현재 판정 중 준수·일탈·질의·확인 필요를 판정 순서대로 옮긴다. 보증값 작성 줄은 데이터시트로
가고, 반려한 판정과 원문 위치가 없는 판정은 넣지 않는다(CR-03). 값은 원문 그대로(CR-10),
후보·팀 가정 표시(CR-06·08).
"""

from io import BytesIO

import psycopg
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from rfp_agent.pipeline import queries
from rfp_agent.pipeline.export import location_text

RESULTS = ("DEVIATION_CANDIDATE", "QUERY_CANDIDATE", "NEEDS_REVIEW", "COMPLY")
# 준수 여부 라벨 (목업 Tbe): 영문, 국문
VERDICT = {
    "COMPLY": ("Comply", "준수"),
    "DEVIATION_CANDIDATE": ("Deviation", "일탈"),
    "QUERY_CANDIDATE": ("Clarification", "질의"),
    "NEEDS_REVIEW": ("To be confirmed", "확인 필요"),
}
STATE = {"en": ("Confirmed", "Candidate", "Team assumption"), "ko": ("확정", "후보", "팀 가정")}
HEADER = {
    "en": ["No.", "Item", "Requirement", "Compliance", "Offered", "Source", "Status"],
    "ko": ["No.", "항목", "고객 요구", "준수 여부", "우리 제품값", "원문 위치", "상태"],
}
INCLUDE = {"all": "후보포함", "confirmed": "확정만"}


class NotApproved(ValueError):
    pass


def _join(*parts: object) -> str:
    return " ".join(str(p) for p in parts if p not in (None, ""))


def with_unit(raw: str | None, unit: str | None) -> str:
    """화면(withUnit)과 같게: 원문에 단위가 이미 있으면 다시 붙이지 않는다."""
    if not raw:
        return ""
    return f"{raw} {unit}" if unit and unit not in raw else raw


def _where(loc: dict) -> str:
    """미리보기의 두 번째 줄: 절 · 표 n번 · n행 (파일 이름은 따로)."""
    no = f" {loc['item_no']}번" if loc["item_no"] else ""
    table = loc["table_name"] + no if loc["table_name"] else ""
    section = _join(loc["section_no"], loc["section_title"])
    line = f"{loc['line_start']}행" if loc["line_start"] else ""
    page = f"{loc['page']}쪽" if loc.get("page") else ""          # PDF 쪽 (add-pdf-page-location)
    return " · ".join(p for p in (page, section, table, line) if p)


def tbe(conn: psycopg.Connection, run_id: int, include: str = "all", lang: str = "en",
        base: str = "now") -> dict:
    """{file_name, rows, counts}. include = all(후보 포함) | confirmed(확정한 줄만)."""
    run = queries.run_summary(conn, run_id)
    if base == "v1" and run["stage"] != "APPROVED":
        raise NotApproved("제출본 v1은 결재가 승인된 뒤에 생깁니다.")
    names = {d["file_no"]: d["file_name"] for d in queries.run_documents(conn, run_id)}
    judged = [j for j in queries.run_judgments(conn, run_id, priority=True, limit=100_000)
              if j["result"] in RESULTS and j["review_status"] != "REJECTED"]
    total = conn.execute(
        "SELECT count(*) FROM judgment WHERE run_id = %s AND is_current AND result = ANY(%s) "
        "AND review_status <> 'REJECTED'", (run_id, list(RESULTS))).fetchone()[0]
    word = STATE["ko" if lang == "ko" else "en"]
    rows = []
    for j in judged:
        confirmed = j["review_status"] in ("CONFIRMED", "EDITED")
        if include == "confirmed" and not confirmed:
            continue
        en = j["item_name_raw"] or j["item_name"] or j["item_key"] or ""
        ko = j["item_name"] or j["item_name_raw"] or j["item_key"] or ""
        offered = with_unit(j["product_value_raw"], j["product_value_unit"])
        if offered and j["product_code"]:
            offered += f" ({j['product_code']})"
        state = word[0] if confirmed else word[1]
        if j["is_assumed"]:
            state += f" · {word[2]}"
        first = j["locations"][0]
        rows.append({
            "no": len(rows) + 1, "judgment_id": j["judgment_id"], "result": j["result"],
            "item": ko if lang == "ko" else en, "item_ko": ko if lang == "both" else None,
            "requirement": with_unit(j["req_value_raw"], j["unit_raw"]) or "—",
            "verdict": VERDICT[j["result"]][1 if lang == "ko" else 0],
            "offered": offered or "—", "confirmed": confirmed, "assumed": j["is_assumed"],
            "status": state,
            "file_name": names.get(first["file_no"], f"파일 {first['file_no']}"),
            "where": _where(first),
            "source": "\n".join(location_text(loc, names) for loc in j["locations"]),
        })
    count = {r: sum(1 for x in rows if x["result"] == r) for r in RESULTS}
    prefix = f"TBE_{run['review_no']}" + ("_v1" if base == "v1" else "")
    return {
        "file_name": f"{prefix}_{INCLUDE[include]}.xlsx", "review_no": run["review_no"],
        "project_name": run.get("project_name"), "review_name": run.get("review_name"),
        "rows": rows,
        "counts": {"rows": len(rows), "comply": count["COMPLY"],
                   "deviation": count["DEVIATION_CANDIDATE"], "query": count["QUERY_CANDIDATE"],
                   "review": count["NEEDS_REVIEW"],
                   "candidates": sum(1 for x in rows if not x["confirmed"]),
                   "no_location": total - len(judged)},
    }


def tbe_xlsx(conn: psycopg.Connection, run_id: int, include: str = "all", lang: str = "en",
             base: str = "now") -> tuple[str, bytes, int]:
    """(파일 이름, 엑셀 바이트, 줄 수)."""
    data = tbe(conn, run_id, include, lang, base)
    wb = Workbook()
    ws = wb.active
    ws.title = "TBE"
    title = " · ".join(x for x in (data["review_no"], data["project_name"],
                                   data["review_name"]) if x)
    ws.append([f"TBE {'준수표' if lang == 'ko' else 'Compliance Sheet'} — {title}"])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append(["Status \"Candidate\"/\"후보\"는 담당 엔지니어가 아직 확정하지 않은 줄입니다. "
               "원문 위치가 없는 판정은 넣지 않았습니다."])
    ws.append([])
    ws.append(HEADER["ko" if lang == "ko" else "en"])
    head = ws.max_row
    for cell in ws[head]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="EEF2F6")
    for r in data["rows"]:
        item = r["item"] + (f"\n{r['item_ko']}" if r["item_ko"] else "")
        ws.append([r["no"], item, r["requirement"], r["verdict"], r["offered"], r["source"],
                   r["status"]])
    for col, width in zip("ABCDEFG", (6, 44, 18, 16, 26, 52, 18), strict=True):
        ws.column_dimensions[col].width = width
    for row in ws.iter_rows(min_row=head + 1):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = ws.cell(row=head + 1, column=1)
    out = BytesIO()
    wb.save(out)
    return data["file_name"], out.getvalue(), len(data["rows"])
