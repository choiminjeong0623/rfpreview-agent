"""FR-11 유형별 담당자 전달. 코드만 쓴다 (CR-01).

요구사항의 주 유형 → 담당 역할(requirement_type.default_role)로 "내 할 일"을 만든다.
기술 검토 엔지니어 몫(기술 성능·위험 조건·규격·설치 환경, 미분류)은 검토 화면에서 보므로
따로 보내지 않는다.
장비마다 반복되는 같은 조건(제조사 자격 등)은 한 건으로 묶어 "같은 조건 N개 장비에 반복"으로 보낸다.
채택(또는 고쳐서 채택)한 제안 포인트는 영업에, 손실 환산 포인트는 견적에도 보낸다 (AR-08).
"""

import re
from collections import defaultdict

import psycopg
from psycopg.rows import dict_row

from rfp_agent.pipeline.structure import normalize

SENT_ROLES = ("COST", "QUALITY", "SALES")
ADOPTED = ("ADOPTED", "EDITED")
POINT_ROLES = {"MARGIN": ("SALES",), "FIELD": ("SALES",), "LOSS": ("SALES", "COST")}
# 다시 만들 때 이어 쓰는 칸: 상태, 만든 시각, 메일 보낸 기록, 회신 기록 (update-role-handoff-mail)
KEPT = ("status", "assignee_id", "sent_at", "updated_at", "mail_sent_at", "mail_to", "sent_by",
        "mail_error", "replied_at", "replied_by", "reply_note", "ask_text", "ask_by")
DEFAULTS = {"status": "TODO"}
PLACES = ", ".join("COALESCE(%s, now())" if c == "sent_at" else "%s" for c in KEPT)
LIST_MARK = re.compile(r"^\s*(?:\(?[0-9a-zA-Z가-힣]{1,3}[.)]\s*|-\s*)")

REQUIREMENTS_SQL = """
    SELECT r.requirement_id, r.text_raw, r.source_kind, tr.item_name_raw, tr.required_raw,
           t.type_code, rt.default_role, d.file_no,
           (SELECT min(l.line_start) FROM requirement_location rl
            JOIN source_location l ON l.location_id = rl.location_id
            WHERE rl.requirement_id = r.requirement_id) AS line_start
    FROM requirement r
    JOIN run_document rd ON rd.document_id = r.document_id AND rd.run_id = %(run)s
    JOIN document d ON d.document_id = r.document_id
    JOIN requirement_type_tag t ON t.requirement_id = r.requirement_id AND t.is_primary
    JOIN requirement_type rt ON rt.type_code = t.type_code
    LEFT JOIN table_row tr ON tr.row_id = r.row_id
    WHERE r.req_kind = 'REQUIREMENT' AND rt.default_role = ANY(%(roles)s)
      AND EXISTS (SELECT 1 FROM requirement_location rl
                  WHERE rl.requirement_id = r.requirement_id)
      AND (r.dedup_of IS NULL OR NOT EXISTS (
            SELECT 1 FROM requirement x JOIN run_document xd ON xd.document_id = x.document_id
            WHERE x.requirement_id = r.dedup_of AND xd.run_id = %(run)s))
    ORDER BY d.file_no, line_start, r.requirement_id"""


def condition_key(row: dict) -> str:
    """같은 조건인지 보는 글.

    표 행은 항목 이름 + 요구값(번호·단위 칸은 뺌), 문장은 목록 표시를 뺀 문장.
    """
    if row["source_kind"] == "TABLE_CELL" and row["item_name_raw"]:
        name = LIST_MARK.sub("", row["item_name_raw"]).rstrip(" .:;")
        text = f"{name} | {row['required_raw'] or ''}"
    else:
        text = LIST_MARK.sub("", row["text_raw"])
    return normalize(text).lower().rstrip(" .:;")


def _requirement_tasks(conn: psycopg.Connection, run_id: int) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(REQUIREMENTS_SQL, {"run": run_id, "roles": list(SENT_ROLES)}).fetchall()
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        groups[(r["default_role"], condition_key(r))].append(r)
    tasks = []
    for (role, key), members in groups.items():
        first = members[0]
        tasks.append({"task_key": f"R|{role}|{key}", "role": role,
                      "requirement_id": first["requirement_id"], "point_id": None,
                      "requirement_ids": [m["requirement_id"] for m in members],
                      "type_code": first["type_code"], "repeat_count": len(members)})
    return tasks


def _point_tasks(conn: psycopg.Connection, run_id: int) -> list[dict]:
    tasks = []
    for point_id, kind, req_id, basis in conn.execute(
            "SELECT point_id, point_kind, requirement_id, basis FROM proposal_point "
            "WHERE run_id = %s AND status = ANY(%s) ORDER BY point_id", (run_id, list(ADOPTED))):
        for role in POINT_ROLES.get(kind, ("SALES",)):
            tasks.append({"task_key": f"P|{role}|{kind}|{req_id}|{basis}", "role": role,
                          "requirement_id": None, "point_id": point_id, "requirement_ids": [],
                          "type_code": None, "repeat_count": 1})
    return tasks


def build_assignments(conn: psycopg.Connection, run_id: int) -> int:
    """할 일을 다시 만든다. 같은 할 일 키면 상태·보낸 기록·회신 요지를 이어 쓴다 (CR-11)."""
    tasks = _requirement_tasks(conn, run_id) + _point_tasks(conn, run_id)
    with conn.cursor(row_factory=dict_row) as cur:
        previous = {r["task_key"]: r for r in cur.execute(
            f"SELECT task_key, {', '.join(KEPT)} FROM assignment WHERE run_id = %s",
            (run_id,)).fetchall()}
    with conn.transaction():
        conn.execute("DELETE FROM assignment WHERE run_id = %s", (run_id,))
        for t in tasks:
            prev = previous.get(t["task_key"], {})
            conn.execute(
                f"""INSERT INTO assignment (run_id, assignee_role, requirement_id, point_id,
                       repeat_count, task_key, requirement_ids, type_code, {', '.join(KEPT)})
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, {PLACES})""",
                (run_id, t["role"], t["requirement_id"], t["point_id"], t["repeat_count"],
                 t["task_key"], t["requirement_ids"], t["type_code"],
                 *[prev.get(c, DEFAULTS.get(c)) for c in KEPT]))
    return len(tasks)
