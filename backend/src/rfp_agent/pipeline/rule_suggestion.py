"""위험 표현 사전에 추가 제안 (change add-rule-suggestion, FR-06 ④).

엔지니어가 검토에서 찾은 놓친 표현을 원문 위치와 함께 제안으로 남기고,
규칙 담당(엔지니어·승인자)이 반영하면 위험 표현 사전에 넣는다(고침 이력, add-rule-editing).
제안만으로는 사전을 바꾸지 않는다.
"""

import psycopg
from psycopg.rows import dict_row

from rfp_agent.pipeline import rule_edit
from rfp_agent.pipeline.evaluation import normalize
from rfp_agent.pipeline.queries import _locations
from rfp_agent.pipeline.review import ReviewError, _user_role, default_user

DICTIONARY = "risk-expressions"
CLOSED_STAGES = ("PROCESSING", "FAILED")

_SELECT = """
    SELECT s.suggestion_id, s.expression, s.note, s.run_id,
           'RV-' || extract(year FROM r.started_at)::int || '-' || lpad(r.run_id::text, 3, '0')
               AS review_no,
           s.requirement_id, s.status, s.suggested_by, su.user_name AS suggested_by_name,
           s.suggested_at, s.decided_by, du.user_name AS decided_by_name, s.decided_at,
           s.decision_reason, s.edit_id
      FROM rule_suggestion s
      JOIN review_run r ON r.run_id = s.run_id
      JOIN app_user su ON su.user_id = s.suggested_by
      LEFT JOIN app_user du ON du.user_id = s.decided_by"""


def _with_locations(conn: psycopg.Connection, rows: list[dict]) -> list[dict]:
    for row in rows:
        row["locations"] = _locations(conn, [row["requirement_id"]], row["run_id"]).get(
            row["requirement_id"], [])
    return [r for r in rows if r["locations"]]       # 위치가 없으면 내지 않는다 (CR-02)


def listing(conn: psycopg.Connection, run_id: int | None = None,
            status: str | None = None) -> list[dict]:
    """제안 목록: 확인 대기 먼저, 그다음 최근 것."""
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(_SELECT + """
             WHERE (%(run)s::int IS NULL OR s.run_id = %(run)s)
               AND (%(status)s::text IS NULL OR s.status = %(status)s)
             ORDER BY s.status <> 'PENDING', s.suggested_at DESC, s.suggestion_id DESC""",
            {"run": run_id, "status": status}).fetchall()
    return _with_locations(conn, rows)


def _one(conn: psycopg.Connection, suggestion_id: int) -> dict:
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute(_SELECT + " WHERE s.suggestion_id = %s", (suggestion_id,)).fetchone()
    if row is None:
        raise ReviewError(404, f"제안 {suggestion_id}이(가) 없습니다.")
    return _with_locations(conn, [row])[0]


def suggest(conn: psycopg.Connection, run_id: int, expression: str, note: str | None = None,
            actor_id: int | None = None) -> dict:
    """놓친 표현을 제안한다. 이 검토 문서에서 표현이 나온 첫 문장을 근거로 붙인다."""
    expr = " ".join((expression or "").split())
    if not 2 <= len(expr) <= 100:
        raise ReviewError(400, "표현은 2자 이상 100자 이하로 넣어 주세요.")
    stage = conn.execute("SELECT stage FROM review_run WHERE run_id = %s", (run_id,)).fetchone()
    if stage is None:
        raise ReviewError(404, f"검토 {run_id}이(가) 없습니다.")
    if stage[0] in CLOSED_STAGES:
        raise ReviewError(409, "분석이 끝난 검토에서만 제안할 수 있습니다.")
    actor_id = actor_id or default_user(conn, "ENGINEER")
    _user_role(conn, actor_id)
    if conn.execute("SELECT 1 FROM risk_expression WHERE active AND lower(expression) = lower(%s)",
                    (expr,)).fetchone():
        raise ReviewError(409, f"'{expr}'은(는) 이미 위험 표현 사전에 있습니다.")
    if conn.execute("SELECT 1 FROM rule_suggestion WHERE status = 'PENDING' "
                    "AND lower(expression) = lower(%s)", (expr,)).fetchone():
        raise ReviewError(409, f"'{expr}'은(는) 이미 제안되어 확인을 기다리고 있습니다.")
    needle = normalize(expr)
    found = next((rid for rid, text in conn.execute(
        """SELECT q.requirement_id, q.text_raw FROM requirement q
            WHERE q.document_id IN (SELECT document_id FROM run_document WHERE run_id = %s)
            ORDER BY q.requirement_id""", (run_id,)) if needle in normalize(text)), None)
    if found is None:
        raise ReviewError(400, "이 검토 문서에서 찾지 못했습니다. 원문 그대로 붙여 넣어 주세요.")
    suggestion_id = conn.execute(
        """INSERT INTO rule_suggestion (expression, note, run_id, requirement_id, suggested_by)
           VALUES (%s, %s, %s, %s, %s) RETURNING suggestion_id""",
        (expr, (note or "").strip() or None, run_id, found, actor_id)).fetchone()[0]
    conn.commit()
    return _one(conn, suggestion_id)


def _pending(conn: psycopg.Connection, suggestion_id: int) -> dict:
    row = _one(conn, suggestion_id)
    if row["status"] != "PENDING":
        raise ReviewError(409, "이미 반영하거나 반려한 제안입니다.")
    return row


def _editor(conn: psycopg.Connection, actor_id: int | None) -> int:
    actor_id = actor_id or default_user(conn, "ENGINEER")
    if _user_role(conn, actor_id) not in rule_edit.EDITOR_ROLES:
        raise ReviewError(403, "제안은 엔지니어·승인자만 반영하거나 반려할 수 있습니다.")
    return actor_id


def accept(conn: psycopg.Connection, suggestion_id: int, value: dict, reason: str | None,
           actor_id: int | None = None) -> dict:
    """위험 표현 사전에 넣고(고침 이력) 제안을 반영으로 바꾼다."""
    row = _pending(conn, suggestion_id)
    actor_id = _editor(conn, actor_id)
    value = {**value, "expression": row["expression"]}
    # 사전 칸이 비면 DB 오류가 나기 전에 막는다(제안은 그대로 대기)
    if value.get("risk_kind") not in rule_edit.RISK_KINDS:
        raise ReviewError(400, "위험 종류를 골라 주세요.")
    if value.get("language") not in rule_edit.LANGUAGES:
        raise ReviewError(400, "언어를 골라 주세요.")
    try:
        with conn.transaction():
            edit = rule_edit.add(conn, DICTIONARY, value, reason, actor_id)
            conn.execute(
                """UPDATE rule_suggestion SET status = 'ACCEPTED', decided_by = %s,
                          decided_at = now(), decision_reason = %s, edit_id = %s
                    WHERE suggestion_id = %s""",
                (actor_id, edit["reason"], edit["edit_id"], suggestion_id))
    except rule_edit.RuleEditError as exc:
        conn.rollback()
        raise ReviewError(exc.status, str(exc)) from exc
    except psycopg.Error as exc:
        conn.rollback()
        raise ReviewError(400, "사전에 넣지 못했습니다. 칸을 확인해 주세요.") from exc
    conn.commit()
    return _one(conn, suggestion_id)


def decline(conn: psycopg.Connection, suggestion_id: int, reason: str | None,
            actor_id: int | None = None) -> dict:
    _pending(conn, suggestion_id)
    actor_id = _editor(conn, actor_id)
    if not (reason or "").strip():
        raise ReviewError(400, "반려 사유를 적어 주세요.")
    conn.execute(
        """UPDATE rule_suggestion SET status = 'DECLINED', decided_by = %s, decided_at = now(),
                  decision_reason = %s WHERE suggestion_id = %s""",
        (actor_id, reason.strip(), suggestion_id))
    conn.commit()
    return _one(conn, suggestion_id)
