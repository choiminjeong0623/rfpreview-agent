"""협조 요청 메일 발송 (FR-11, update-role-handoff-mail). 고르기·묶기는 코드만 한다 (CR-01).

- 판정 확정 뒤: 연결된 요구사항의 현재 판정이 모두 사람 확인되었고(후보 없음)
  아직 보내지 않은 요청,
  채택한 제안 포인트 요청을 부서별로 한 통에 모아 보낸다.
  사람이 보지 않은 후보는 나가지 않는다 (CR-08).
- 판정이 없는 요청과 발송 실패·주소 없음 요청은 엔지니어가
  [보내기]·[다시 보내기]로 보낸다.
- 같은 요청은 한 번만 보낸다(mail_sent_at). 원문 위치가 없는 요청은 넣지 않는다 (CR-02).
- 팀 가정 값이 들어간 요청에는 "팀 가정"을 붙인다 (CR-06).
- 요청마다 부서 관점 "확인할 점" 한 문장을 AI가 쓴다(add-handoff-questions, C4).
  숫자·경쟁 비교가 있거나 AI가 없거나 실패하면 부서 기본 문장(CODE). 메일은 멈추지 않는다.
"""

from collections import defaultdict
from datetime import date, timedelta
from email.message import EmailMessage
from io import BytesIO

import psycopg
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font

from rfp_agent.llm import tasks
from rfp_agent.llm.client import LLMFailure
from rfp_agent.notify.mail import MailFailure, get_mailer, send_with_retry
from rfp_agent.pipeline import queries
from rfp_agent.pipeline.export import location_text

DEPT_NAMES = {"COST": "견적 담당", "QUALITY": "품질 담당", "SALES": "영업 담당"}
POINT_KIND_NAMES = {"MARGIN": "여유", "LOSS": "손실 환산", "FIELD": "현장 이력"}
REPLY_DAYS = 3                  # 회신 기한: 보낸 날 + 3일 (SCR-13 목업 규칙)
NO_ADDRESS = "주소 없음"
ASK_DEFAULTS = {
    "COST": "견적 금액이나 조건(비용·일정·보증)에 반영할 것이 있는지 확인 부탁드립니다.",
    "QUALITY": "시험·성적서·인증 요구를 맞출 수 있는지 확인 부탁드립니다.",
    "SALES": "고객과 협의하거나 계약 조건으로 정리할 것이 있는지 확인 부탁드립니다.",
}
ASK_MARK = {"AI": "AI 작성", "CODE": "기본 문장"}
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# 판정 확정 뒤 자동으로 보낼 요청: 안 보냄, 오류 기록 없음,
# 판정이 모두 사람 확인됨(또는 채택한 제안 포인트)
READY_SQL = """
    SELECT a.assignment_id FROM assignment a
    WHERE a.run_id = %(run)s AND a.status = 'TODO' AND a.mail_sent_at IS NULL
      AND a.mail_error IS NULL
      AND (a.point_id IS NOT NULL OR (
            EXISTS (SELECT 1 FROM judgment j WHERE j.run_id = a.run_id AND j.is_current
                    AND j.requirement_id = ANY(a.requirement_ids))
            AND NOT EXISTS (SELECT 1 FROM judgment j WHERE j.run_id = a.run_id AND j.is_current
                    AND j.requirement_id = ANY(a.requirement_ids)
                    AND j.review_status = 'CANDIDATE')))
    ORDER BY a.assignment_id"""


def ready_ids(conn: psycopg.Connection, run_id: int) -> list[int]:
    return [r[0] for r in conn.execute(READY_SQL, {"run": run_id})]


def _kind(a: dict) -> str:
    if a["point_kind"]:
        return f"{POINT_KIND_NAMES.get(a['point_kind'], a['point_kind'])} 제안 포인트"
    kind = a["type_name"] or ""
    return f"{kind} · 같은 조건 {a['repeat_count']}곳" if a["repeat_count"] > 1 else kind


def questions(llm, role: str, items: list[dict]) -> list[tuple[str, str]]:
    """요청마다 (확인할 점, 쓴 이 AI·CODE). 검사에 걸린 줄·AI 없음·실패는 부서 기본 문장."""
    answers: list[str | None] = [None] * len(items)
    if llm is not None and items:
        try:
            answers = tasks.department_questions(llm, role, [a["text"] for a in items])
        except LLMFailure:
            answers = [None] * len(items)        # 메일은 기본 문장으로 보낸다
    return [(q, "AI") if q else (ASK_DEFAULTS[role], "CODE") for q in answers]


def _rows(items: list[dict], names: dict[int, str],
          asks: list[tuple[str, str]]) -> list[list[str]]:
    return [[str(n), _kind(a), " ".join(a["text"].split()),
             "\n".join(location_text(loc, names) for loc in a["locations"]),
             "팀 가정" if a["is_assumed"] else "", f"{ask} ({ASK_MARK[by]})"]
            for n, (a, (ask, by)) in enumerate(zip(items, asks, strict=True), start=1)]


def _workbook(title: str, rows: list[list[str]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "협조 요청"
    ws.append([title])
    ws["A1"].font = Font(bold=True)
    ws.append(["No.", "요청 종류", "요구사항", "원문 위치", "팀 가정", "확인할 점", "회신"])
    for c in ws[2]:
        c.font = Font(bold=True)
    for r in rows:
        ws.append([*r, ""])
    for col, width in zip("ABCDEFG", (6, 22, 70, 40, 10, 50, 30), strict=True):
        ws.column_dimensions[col].width = width
    for line in ws.iter_rows(min_row=3):
        for c in line:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    out = BytesIO()
    wb.save(out)
    return out.getvalue()


def build_message(run: dict, role: str, items: list[dict], names: dict[int, str],
                  sender: str, to: str, today: date,
                  asks: list[tuple[str, str]] | None = None) -> EmailMessage:
    """제목(검토 번호·사업명), 본문(마감·회신 기한·요청마다 요구사항·원문 위치·팀 가정), 엑셀."""
    dept = DEPT_NAMES[role]
    project = run.get("project_name") or run.get("review_name") or ""
    reply_by = today + timedelta(days=REPLY_DAYS)
    asks = asks or [(ASK_DEFAULTS[role], "CODE")] * len(items)
    rows = _rows(items, names, asks)
    lines = [f"{dept} 담당자께,", "",
             f"검토 {run['review_no']}{f' ({project})' if project else ''}에서 확인을 부탁드릴 "
             f"요청 {len(items)}건을 보냅니다.",
             f"제출 마감: {run.get('due_date') or '정하지 않음'} · "
             f"회신 기한: {reply_by.isoformat()}",
             "기술 검토 엔지니어가 확인한 뒤 보낸 요청입니다. "
             "\"팀 가정\"은 팀이 정한 값이 들어간 항목이니 확정 값으로 회신해 주세요.",
             "\"확인할 점\"은 참고 문장이고(AI 작성 또는 기본 문장) "
             "판단은 요구사항 원문 기준입니다.",
             ""]
    for no, kind, text, where, assumed, ask in rows:
        lines.append(f"{no}. [{kind}]{' (팀 가정)' if assumed else ''}")
        lines.append(f"   요구사항: {text if len(text) <= 300 else text[:300] + '…'}")
        lines.append(f"   원문 위치: {where.replace(chr(10), ' / ')}")
        lines.append(f"   확인할 점: {ask}")
    lines += ["", "같은 내용을 엑셀로 붙였습니다. 회신 칸에 적어 이 메일에 답장해 주세요.",
              f"보낸 사람: {run.get('engineer_name') or '기술 검토 엔지니어'} (RFP 검토 시스템)"]
    msg = EmailMessage()
    msg["Subject"] = f"[협조 요청] {run['review_no']} {project}".strip()
    msg["From"] = sender
    msg["To"] = to
    msg.set_content("\n".join(lines))
    title = f"{run['review_no']} {dept} 협조 요청"
    main, sub = XLSX.split("/")
    msg.add_attachment(_workbook(title, rows), maintype=main, subtype=sub,
                       filename=f"협조요청_{run['review_no']}_{role}.xlsx")
    return msg


def send_requests(conn: psycopg.Connection, run_id: int, assignment_ids: list[int],
                  actor_id: int, llm=None, resend: bool = False) -> dict:
    """고른 요청 가운데 아직 보내지 않은 것을 부서별로 한 통씩 보낸다. 결과 수를 돌려준다.

    resend면 메일 보냄(회신 대기) 요청도 다시 보낸다 (엔지니어 재요청, update-todo-search).
    자동 발송(send_after_confirm)은 resend 없이 부르므로 같은 요청은 한 번만 나간다."""
    from rfp_agent.pipeline.review import assignments_for, log  # review가 이 모듈을 부른다

    wanted = set(assignment_ids)
    if not wanted:
        return {"sent": 0, "failed": 0, "no_address": 0, "mails": 0}
    run = queries.run_summary(conn, run_id)
    names = {d["file_no"]: d["file_name"] for d in queries.run_documents(conn, run_id)}
    mailer = get_mailer()
    by_role: dict[str, list[dict]] = defaultdict(list)
    for role in DEPT_NAMES:
        for a in assignments_for(conn, role, run_id):    # 원문 위치 없는 요청은 이미 빠진다
            if a["assignment_id"] in wanted and (
                    a["status"] == "TODO" or (resend and a["status"] == "DOING")):
                by_role[role].append(a)
    out = {"sent": 0, "failed": 0, "no_address": 0, "mails": 0}
    for role, items in by_role.items():
        ids = [a["assignment_id"] for a in items]
        to = mailer.address(role)
        if not to:
            conn.execute("UPDATE assignment SET mail_error = %s WHERE assignment_id = ANY(%s)",
                         (NO_ADDRESS, ids))
            out["no_address"] += len(ids)
            continue
        asks = questions(llm, role, items)
        message = build_message(run, role, items, names, mailer.sender(), to, date.today(), asks)
        try:
            send_with_retry(mailer, message)
        except MailFailure as exc:
            conn.execute("UPDATE assignment SET mail_error = %s WHERE assignment_id = ANY(%s)",
                         (str(exc), ids))
            out["failed"] += len(ids)
            continue
        conn.execute(
            """UPDATE assignment SET status = 'DOING', mail_sent_at = now(), mail_to = %s,
                      sent_by = %s, mail_error = NULL, updated_at = now()
               WHERE assignment_id = ANY(%s)""", (to, actor_id, ids))
        for a, (ask, by) in zip(items, asks, strict=True):
            conn.execute("UPDATE assignment SET ask_text = %s, ask_by = %s "
                         "WHERE assignment_id = %s", (ask, by, a["assignment_id"]))
        log(conn, run_id, "assignment", ids[0], "SEND", None,
            {"dept": role, "mail_to": to, "count": len(ids),
             "subject": message["Subject"], **({"resend": True} if resend else {})},
            None, actor_id)
        out["sent"] += len(ids)
        out["mails"] += 1
    conn.commit()
    return out


def send_after_confirm(conn: psycopg.Connection, run_id: int, actor_id: int,
                       llm=None) -> dict:
    """판정 확정·제안 포인트 채택 뒤 보낼 수 있게 된 요청만 보낸다."""
    return send_requests(conn, run_id, ready_ids(conn, run_id), actor_id, llm)
