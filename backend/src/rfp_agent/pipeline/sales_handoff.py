"""영업 인계 (add-submission-package, FR-11 확장). 고르기·조건 판단은 코드만 한다 (CR-01).

- 데이터시트: 엔지니어가 넘기면 그 표의 엑셀을 영업 주소로 보낸다.
  후보 칸이 남으면 넘기지 않는다(CR-08). 확인 필요 칸은 비운 채로 넘긴다(CR-04).
- 인계 패키지: 결재 승인 뒤 일탈 목록·질의서 Word, TBE(v1)·데이터시트 엑셀, 목록 파일을 zip 하나로.
  기존 내보내기 함수를 그대로 써서 화면에서 내려받은 파일과 같다(CR-11).
- 넘긴 기록은 sales_handoff에, 이력은 review_log SEND에 남긴다. 실패도 한 줄 (CR-12).
"""

import zipfile
from email.message import EmailMessage
from io import BytesIO

import psycopg
from psycopg.rows import dict_row

from rfp_agent.notify.mail import MailFailure, get_mailer, send_with_retry
from rfp_agent.pipeline import datasheet, queries, tbe
from rfp_agent.pipeline.export import outputs_docx
from rfp_agent.pipeline.handoff_mail import NO_ADDRESS, XLSX

ZIP = "application/zip"
# 담당자 확인 전(처리 중·실패)은 넘기지 않음
SENDABLE = ("ENGINEER_REVIEW", "APPROVAL", "APPROVED")
LIST_NAMES = {"DEVIATION": "일탈 목록", "QUERY": "질의서"}


class HandoffRefused(ValueError):
    """넘길 수 없는 상태 (409)."""


def _project(run: dict) -> str:
    return run.get("project_name") or run.get("review_name") or ""


def _message(run: dict, subject: str, lines: list[str], to: str, sender: str) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = f"{subject} {run['review_no']} {_project(run)}".strip()
    msg["From"] = sender
    msg["To"] = to
    msg.set_content("\n".join(["영업 담당자께,", "", *lines, "",
                               f"보낸 사람: {run.get('engineer_name') or '기술 검토 엔지니어'} "
                               "(RFP 검토 시스템)"]))
    return msg


def _deliver(conn: psycopg.Connection, run: dict, kind: str, table_id: int | None,
             files: list[str], build, actor_id: int) -> dict:
    """주소를 찾아 보내고 기록을 남긴다. build(to, sender) → EmailMessage."""
    from rfp_agent.pipeline.review import log  # review가 handoff_mail을 부르므로 늦게 부른다

    mailer = get_mailer()
    to = mailer.address("SALES")
    error = None
    if not to:
        error = NO_ADDRESS
    else:
        try:
            send_with_retry(mailer, build(to, mailer.sender()))
        except MailFailure as exc:
            error = str(exc)
    handoff_id = conn.execute(
        """INSERT INTO sales_handoff (run_id, kind, table_id, file_names, mail_to, mail_error,
                                      sent_by)
           VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING handoff_id""",
        (run["run_id"], kind, table_id, files, to, error, actor_id)).fetchone()[0]
    log(conn, run["run_id"], "sales_handoff", handoff_id, "SEND", None,
        {"kind": kind, "table_id": table_id, "mail_to": to, "files": files, "error": error},
        None, actor_id)
    conn.commit()
    return {"handoff_id": handoff_id, "sent": error is None, "mail_to": to, "error": error}


def send_datasheet(conn: psycopg.Connection, run_id: int, table_id: int, actor_id: int) -> dict:
    run = queries.run_summary(conn, run_id)
    if run["stage"] not in SENDABLE:
        raise HandoffRefused("담당자 확인 단계부터 영업에 넘길 수 있습니다.")
    data = datasheet.datasheet(conn, run_id, table_id)      # 없으면 NotFound
    counts = data["counts"]
    if counts["cand"]:
        raise HandoffRefused(f"후보 {counts['cand']}칸을 먼저 확정해 주세요. "
                             "사람이 확인하지 않은 값은 넘기지 않습니다.")
    name, body, _ = datasheet.datasheet_xlsx(conn, run_id, table_id)

    def build(to: str, sender: str) -> EmailMessage:
        msg = _message(run, "[데이터시트]", [
            f"검토 {run['review_no']}의 데이터시트 \"{data['table_name']}\""
            f"({data['source_file']})를 넘깁니다.",
            f"칸 {counts['rows']}개 중 확정 {counts['ok']}칸, "
            f"확인 필요 {counts['empty']}칸(근거 값이 없어 비워 둠).",
            "고객 양식의 칸 순서 그대로입니다. 비운 칸은 채우지 말고 엔지니어에게 확인해 주세요.",
        ], to, sender)
        main, sub = XLSX.split("/")
        msg.add_attachment(body, maintype=main, subtype=sub, filename=name)
        return msg

    out = _deliver(conn, run, "DATASHEET", table_id, [name], build, actor_id)
    return {**out, "empty": counts["empty"], "files": [name]}


def _approved_at(conn: psycopg.Connection, run_id: int):
    row = conn.execute("SELECT decided_at FROM approval WHERE run_id = %s "
                       "AND decision = 'APPROVED' ORDER BY decided_at DESC LIMIT 1",
                       (run_id,)).fetchone()
    return row[0] if row else None


def build_package(conn: psycopg.Connection, run_id: int) -> tuple[str, bytes, list[str]]:
    """(zip 이름, zip 바이트, 담은 파일 이름). 승인 전이면 HandoffRefused."""
    run = queries.run_summary(conn, run_id)
    if run["stage"] != "APPROVED":
        raise HandoffRefused("인계 패키지는 결재 승인 뒤에 만들 수 있습니다.")
    files: list[tuple[str, bytes]] = []
    left_out: list[str] = []
    for kind, label in LIST_NAMES.items():
        if any(i["status"] != "REMOVED" for i in queries.run_outputs(conn, run_id, kind)):
            files.append(outputs_docx(conn, run_id, kind))
        else:
            left_out.append(f"{label}: {'일탈' if kind == 'DEVIATION' else '질의'} 후보 없음")
    try:
        name, body, _ = tbe.tbe_xlsx(conn, run_id, "all", "en", "v1")
        files.append((name, body))
    except tbe.NotApproved as exc:                  # 승인했으면 생기지 않지만 빼고 이유를 적는다
        left_out.append(f"TBE 준수표: {exc}")
    sheets = datasheet.datasheets(conn, run_id)
    for s in sheets:
        name, body, _ = datasheet.datasheet_xlsx(conn, run_id, s["table_id"])
        files.append((name, body))
    if not sheets:
        left_out.append("데이터시트: 판정이 있는 고객 표 없음")
    approved = _approved_at(conn, run_id)
    project = f" · {_project(run)}" if _project(run) else ""
    when = approved.isoformat(timespec="minutes") if approved else "—"
    readme = [f"인계 패키지 · {run['review_no']}{project}", f"결재 승인: {when}",
              "제출본 v1(승인 시점 판정) 기준입니다. "
              "\"후보\"·\"확인 필요\" 표시는 그대로 두었습니다.",
              "", "담은 파일:", *[f"- {n}" for n, _ in files]]
    if left_out:
        readme += ["", "뺀 것:", *[f"- {x}" for x in left_out]]
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, b in files:
            z.writestr(n, b)
        z.writestr("목록.txt", "\n".join(readme) + "\n")
    names = [n for n, _ in files] + ["목록.txt"]
    return f"인계패키지_{run['review_no']}.zip", buf.getvalue(), names


def send_package(conn: psycopg.Connection, run_id: int, actor_id: int) -> dict:
    run = queries.run_summary(conn, run_id)
    zip_name, body, names = build_package(conn, run_id)

    def build(to: str, sender: str) -> EmailMessage:
        msg = _message(run, "[영업 인계]", [
            f"결재가 승인된 검토 {run['review_no']}의 인계 패키지를 보냅니다.",
            f"제출 마감: {run.get('due_date') or '정하지 않음'}",
            "zip 안의 파일:", *[f"- {n}" for n in names],
            "\"목록.txt\"에 뺀 것과 그 이유를 적었습니다.",
        ], to, sender)
        main, sub = ZIP.split("/")
        msg.add_attachment(body, maintype=main, subtype=sub, filename=zip_name)
        return msg

    out = _deliver(conn, run, "PACKAGE", None, names, build, actor_id)
    return {**out, "empty": None, "files": names}


def handoffs(conn: psycopg.Connection, run_id: int) -> list[dict]:
    """넘긴 기록, 최근 것부터."""
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            """SELECT h.handoff_id, h.kind, h.table_id, h.file_names, h.mail_to, h.mail_error,
                      h.sent_at, h.sent_by, u.user_name AS sent_by_name
               FROM sales_handoff h JOIN app_user u ON u.user_id = h.sent_by
               WHERE h.run_id = %s ORDER BY h.sent_at DESC, h.handoff_id DESC""",
            (run_id,)).fetchall()
