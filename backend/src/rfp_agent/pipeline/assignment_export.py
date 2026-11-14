"""협조 요청 엑셀 내보내기 (SCR-13 "내보내기", change update-todo-search).

화면이 거른 요청 번호를 받아 그 요청만 엑셀 한 장에 담는다. 거르기는 화면이 하고,
여기서는 번호로 고르기만 한다(같은 목록 API를 쓰므로 원문 위치가 없는 요청은 이미 빠진다, CR-02).
팀 가정 값이 든 요청 줄에는 "팀 가정"을 적는다(CR-06). 내보낸 시각은 넣지 않는다(CR-11).
"""

from datetime import timedelta
from io import BytesIO

import psycopg
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from rfp_agent.pipeline.export import location_text
from rfp_agent.pipeline.handoff_mail import DEPT_NAMES, REPLY_DAYS
from rfp_agent.pipeline.review import assignments_for

HEADERS = ("No.", "검토 번호", "검토 이름", "사업명", "수신 부서", "상태", "요구사항",
           "원문 위치", "팀 가정", "보낸 주소", "보낸 일시", "회신 기한", "회신 받음", "회신 요지")
WIDTHS = (6, 14, 24, 24, 12, 12, 60, 36, 10, 26, 18, 12, 18, 40)
HEAD_FILL = PatternFill("solid", fgColor="EEF2F6")
STATUS = {"TODO": "안 보냄", "DOING": "메일 보냄", "DONE": "회신 받음"}


class NothingToExport(ValueError):
    """고른 요청이 없음."""


def _when(v) -> str:
    return v.strftime("%Y-%m-%d %H:%M") if v else ""


def assignments_xlsx(conn: psycopg.Connection, role: str | None,
                     assignment_ids: list[int]) -> tuple[str, bytes, int]:
    """(파일 이름, 엑셀 바이트, 줄 수). 줄 순서는 목록 API와 같다."""
    wanted = set(assignment_ids)
    if not wanted:
        raise NothingToExport("내보낼 요청을 고르세요.")
    items = [a for a in assignments_for(conn, role) if a["assignment_id"] in wanted]
    if not items:
        raise NothingToExport("고른 요청이 목록에 없습니다.")
    names: dict[tuple[int, int], str] = {
        (r, f): n for r, f, n in conn.execute(
            "SELECT rd.run_id, d.file_no, d.file_name FROM run_document rd "
            "JOIN document d USING (document_id) WHERE rd.run_id = ANY(%s)",
            (list({a["run_id"] for a in items}),))}
    dept = DEPT_NAMES[role] if role else "전체"
    wb = Workbook()
    ws = wb.active
    ws.title = "협조 요청"
    ws.append([f"협조 요청 — {dept} · {len(items)}건"])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append(["회신 기한은 보낸 날 + 3일입니다. \"팀 가정\"은 팀이 정한 값이 들어간 요청입니다."])
    ws.append([])
    ws.append(list(HEADERS))
    head = ws.max_row
    for c in ws[head]:
        c.font = Font(bold=True)
        c.fill = HEAD_FILL
    for n, a in enumerate(items, start=1):
        file_names = {f: nm for (r, f), nm in names.items() if r == a["run_id"]}
        sent = a["mail_sent_at"]
        ws.append([
            n, a["review_no"], a["review_name"] or "", a["project_name"] or "",
            DEPT_NAMES.get(a["assignee_role"], a["assignee_role"]),
            STATUS.get(a["status"], a["status"]), " ".join((a["text"] or "").split()),
            "\n".join(location_text(loc, file_names) for loc in a["locations"]),
            "팀 가정" if a["is_assumed"] else "", a["mail_to"] or "", _when(sent),
            (sent + timedelta(days=REPLY_DAYS)).strftime("%Y-%m-%d") if sent else "",
            _when(a["replied_at"]), a["reply_note"] or ""])
    for i, w in enumerate(WIDTHS, start=1):
        ws.column_dimensions[ws.cell(row=head, column=i).column_letter].width = w
    for line in ws.iter_rows(min_row=head + 1):
        for c in line:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = ws.cell(row=head + 1, column=1)
    out = BytesIO()
    wb.save(out)
    return f"협조요청_{dept}.xlsx", out.getvalue(), len(items)
