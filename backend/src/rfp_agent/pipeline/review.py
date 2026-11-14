"""FR-10 담당자 확인·승인과 수정 이력.

멈춤 지점은 두 곳이다. 처리를 마친 실행은 담당자 확인(ENGINEER_REVIEW)에서 멈추고, 엔지니어가
결재자와 상신 의견을 넣어 결재 상신하면 승인 기준(AR-01·02·03·06·07·08)을 코드로 판단해 기록하고
걸린 기준과 관계없이 승인(APPROVAL)에서 멈춘다. 지정된 결재자만 결정한다. 사람이 확인하지 않은
결과는 확정되지 않는다 (CR-08). 모든 동작은 review_log에 남는다.
"""

import json
from dataclasses import dataclass
from decimal import Decimal

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from rfp_agent.notify.mail import get_mailer
from rfp_agent.pipeline import graph_flow, queries
from rfp_agent.pipeline.assignments import build_assignments
from rfp_agent.pipeline.handoff_mail import send_after_confirm
from rfp_agent.pipeline.numbers import fill
from rfp_agent.pipeline.outputs import build_outputs, check_submission
from rfp_agent.pipeline.proposals import build_proposals
from rfp_agent.pipeline.run import RunContext, readable_documents
from rfp_agent.pipeline.warranty import build_warranty

RESULTS = ("COMPLY", "DEVIATION_CANDIDATE", "QUERY_CANDIDATE", "NEEDS_REVIEW", "WARRANTY_TO_FILL")
# 대상 표 → 할 수 있는 동작
ACTIONS = {
    "judgment": {"CONFIRM", "EDIT", "REJECT", "QUERY_SENT", "QUERY_UNSENT"},
    "warranty_candidate": {"CONFIRM", "EDIT", "REJECT"},
    "output_item": {"CONFIRM", "EDIT", "REJECT"},
    "proposal_point": {"ADOPT", "DISCARD", "EDIT"},
    "risk_flag": {"CONFIRM", "REJECT"},
}
KEYS = {"judgment": "judgment_id", "warranty_candidate": "candidate_id",
        "output_item": "item_id", "proposal_point": "point_id", "risk_flag": "risk_id",
        "loss_calc": "loss_calc_id"}
NEEDS_REASON = {"EDIT", "REJECT", "DISCARD"}
# 질의 보냄 표시·되돌리기 (add-query-sent): 질의 후보 판정에만, 엔지니어만.
# 판정 결과를 바꾸지 않으므로 보증값·목록을 다시 만들지 않는다
QUERY_ACTIONS = {"QUERY_SENT", "QUERY_UNSENT"}
DELIVERED_POINTS = ("ADOPTED", "EDITED")         # 채택한(고쳐 채택한) 제안 포인트만 전달 (AR-08)


class ReviewError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


@dataclass
class Criterion:
    ar_code: str
    detail: str


def _json(row: dict | None) -> Jsonb | None:
    if row is None:
        return None
    return Jsonb(json.loads(json.dumps(
        row, default=lambda v: float(v) if isinstance(v, Decimal) else str(v))))


def default_user(conn: psycopg.Connection, role: str) -> int:
    row = conn.execute("SELECT min(user_id) FROM app_user WHERE role = %s", (role,)).fetchone()
    if row[0] is None:
        raise ReviewError(400, f"{role} 역할 사용자가 없습니다.")
    return row[0]


def _user_role(conn: psycopg.Connection, user_id: int, missing: int = 400) -> str:
    row = conn.execute("SELECT role FROM app_user WHERE user_id = %s", (user_id,)).fetchone()
    if row is None:
        raise ReviewError(missing, f"사용자 {user_id}이(가) 없습니다.")
    return row[0]


def _stage(conn: psycopg.Connection, run_id: int) -> str:
    row = conn.execute("SELECT stage FROM review_run WHERE run_id = %s", (run_id,)).fetchone()
    if row is None:
        raise ReviewError(404, f"검토 실행 {run_id}이(가) 없습니다.")
    return row[0]


def require_stage(conn: psycopg.Connection, run_id: int, *stages: str) -> None:
    stage = _stage(conn, run_id)
    if stage not in stages:
        names = {"ENGINEER_REVIEW": "담당자 확인", "APPROVAL": "승인 대기",
                 "REJECTED": "반려됨"}
        raise ReviewError(409, f"지금 단계({stage})에서는 할 수 없습니다. "
                               f"{' / '.join(names.get(s, s) for s in stages)} 단계에서만 됩니다.")


def row(conn: psycopg.Connection, target: str, target_id: int, run_id: int) -> dict:
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute(f"SELECT * FROM {target} WHERE {KEYS[target]} = %s AND run_id = %s",
                          (target_id, run_id)).fetchone()
    if row is None:
        raise ReviewError(404, f"{target} {target_id}이(가) 이 실행에 없습니다.")
    return row


def log(conn: psycopg.Connection, run_id: int, target: str, target_id: int, action: str,
        before: dict | None, after: dict | None, reason: str | None, actor_id: int) -> None:
    conn.execute(
        """INSERT INTO review_log (run_id, target_table, target_id, action, before_value,
                                   after_value, reason, actor_id)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
        (run_id, target, target_id, action, _json(before), _json(after), reason, actor_id))


def _checked_text(text: str, evidence: str) -> tuple[str, str, str | None]:
    """엔지니어가 고친 문장도 숫자를 근거(원래 문장의 숫자)와 대조한다 (CR-07)."""
    filled = fill(text, {"evidence": evidence})
    return filled.text, filled.check, filled.detail


def _apply(conn: psycopg.Connection, target: str, row: dict, action: str,
           value: dict) -> None:
    key, target_id = KEYS[target], row[KEYS[target]]

    def update(sets: dict) -> None:
        cols = ", ".join(f"{c} = %s" for c in sets)
        conn.execute(f"UPDATE {target} SET {cols} WHERE {key} = %s", (*sets.values(), target_id))

    if target == "judgment" and action in QUERY_ACTIONS:
        if row["result"] != "QUERY_CANDIDATE":
            raise ReviewError(409, "질의 보냄은 질의 후보 판정에만 표시할 수 있습니다.")
        if row["review_status"] == "REJECTED":
            raise ReviewError(409, "반려한 판정에는 질의 보냄을 표시할 수 없습니다.")
        sent = row["query_sent_at"] is not None
        if action == "QUERY_SENT" and sent:
            raise ReviewError(409, "이미 질의 보냄으로 표시한 판정입니다.")
        if action == "QUERY_UNSENT" and not sent:
            raise ReviewError(409, "질의 보냄으로 표시하지 않은 판정입니다.")
        if action == "QUERY_SENT":
            update({"query_sent_by": value["actor_id"]})
            conn.execute("UPDATE judgment SET query_sent_at = now() WHERE judgment_id = %s",
                         (target_id,))
        else:
            update({"query_sent_at": None, "query_sent_by": None})
    elif target == "judgment":
        if action == "CONFIRM":
            update({"review_status": "CONFIRMED"})
        elif action == "REJECT":
            update({"review_status": "REJECTED"})
        else:
            result = value.get("result")
            if result not in RESULTS:
                raise ReviewError(400, f"판정 값은 {', '.join(RESULTS)} 중 하나입니다.")
            keep_margin = result == "COMPLY" and row["result"] == "COMPLY"
            update({"result": result, "reason_code": "ENGINEER",
                    "reason_text": "엔지니어 수정", "review_status": "EDITED",
                    "margin_value": row["margin_value"] if keep_margin else None,
                    "margin_kind": row["margin_kind"] if keep_margin else None,
                    "margin_direction": row["margin_direction"] if keep_margin else "NOT_CALC"})
    elif target == "warranty_candidate":
        if action == "CONFIRM":
            if row["candidate_value"] is None:
                raise ReviewError(400, "빈 후보는 확정할 수 없습니다. 값을 넣어(수정) 주세요.")
            update({"status": "CONFIRMED"})
        elif action == "REJECT":
            update({"status": "REJECTED"})
        else:
            text = str(value.get("value") or "").strip()
            if not text:
                raise ReviewError(400, "보증값을 넣어 주세요.")
            update({"candidate_value": text[:200], "candidate_unit": value.get("unit"),
                    "source_kind": "ENGINEER", "status": "CONFIRMED", "reason_code": None,
                    "is_assumed": False})
    elif target == "output_item":
        if action == "CONFIRM":
            update({"status": "CONFIRMED"})
        elif action == "REJECT":
            update({"status": "REMOVED"})
        else:
            text, check, detail = _checked_text(_text(value), row["text_draft"])
            update({"text_draft": text, "number_check": check, "number_detail": detail,
                    "drafted_by": "ENGINEER", "status": "CONFIRMED"})
    elif target == "proposal_point":
        if action == "ADOPT":
            update({"status": "ADOPTED"})
        elif action == "DISCARD":
            update({"status": "DISCARDED"})
        else:
            text, check, detail = _checked_text(_text(value), row["text_draft"])
            if row["is_assumed"] and "팀 가정" not in text:
                text += " (팀 가정)"                    # 팀 가정 표시는 지우지 못한다 (CR-06)
            update({"text_draft": text, "number_check": check, "number_detail": detail,
                    "drafted_by": "ENGINEER", "status": "EDITED"})
    elif target == "risk_flag":
        update({"status": "CONFIRMED" if action == "CONFIRM" else "CLOSED_OK"})


def _text(value: dict) -> str:
    text = str(value.get("text") or "").strip()
    if not text:
        raise ReviewError(400, "고친 문장을 넣어 주세요.")
    return text


def bulk_confirm(ctx: RunContext, run_id: int, judgment_ids: list[int],
                 actor_id: int | None = None) -> dict:
    """여러 현재 판정을 한 번에 제안대로 확정한다. 줄마다 이력을 남기고 다시 만들기는 한 번.

    하나라도 이 실행의 현재 판정이 아니면 아무것도 바꾸지 않는다.
    """
    conn = ctx.conn
    ids = list(dict.fromkeys(judgment_ids))         # 같은 줄을 두 번 보내도 한 번만
    if not ids:
        raise ReviewError(400, "확정할 판정을 하나 이상 고르세요.")
    require_stage(conn, run_id, "ENGINEER_REVIEW")
    actor_id = actor_id or default_user(conn, "ENGINEER")
    _user_role(conn, actor_id)
    befores = [row(conn, "judgment", i, run_id) for i in ids]
    if stale := [b["judgment_id"] for b in befores if not b["is_current"]]:
        raise ReviewError(409, f"현재 판정이 아닌 줄이 있습니다 ({', '.join(map(str, stale))}).")
    # 사람이 한 줄씩 봐야 하는 줄은 빼고 확정한다 (update-bulk-confirm-guard)
    risky = _bulk_risks(conn, run_id, ids)
    skipped = [{"judgment_id": i, "reason": risky[i]} for i in ids if i in risky]
    befores = [b for b in befores if b["judgment_id"] not in risky]
    if not befores:
        raise ReviewError(400, "한꺼번에 확정할 수 있는 줄이 없습니다. 검산 위반·숫자 불일치·"
                               "값이 빈 줄은 한 줄씩 확인해 확정하세요.")
    for before in befores:
        _apply(conn, "judgment", before, "CONFIRM", {})
        after = row(conn, "judgment", before["judgment_id"], run_id)
        log(conn, run_id, "judgment", before["judgment_id"], "CONFIRM", before, after, None,
            actor_id)
    conn.commit()
    docs = readable_documents(conn, [r[0] for r in conn.execute(
        "SELECT document_id FROM run_document WHERE run_id = %s", (run_id,))])
    build_warranty(conn, run_id)
    build_outputs(conn, run_id, docs, ctx.llm)
    build_proposals(conn, run_id, ctx.llm)
    build_assignments(conn, run_id)
    conn.commit()
    send_after_confirm(conn, run_id, actor_id, ctx.llm)  # 확인을 마친 요청은 부서로 메일
    return {"confirmed": len(befores), "skipped": skipped,
            "submission_check": _latest_check(conn, run_id)}


def _bulk_risks(conn: psycopg.Connection, run_id: int, ids: list[int]) -> dict[int, str]:
    """판정 번호 → 한꺼번에 확정에서 뺄 이유. 이유가 여럿이면 CHECK → MISMATCH → NO_VALUE 순."""
    found: dict[int, str] = {}
    for reason, sql in (
        ("CHECK", """SELECT j.judgment_id FROM judgment j
                     JOIN engineering_check c ON c.run_id = j.run_id AND c.result <> 'PASS'
                     JOIN req_value v ON v.value_id IN (c.peak_value_id, c.ik_value_id)
                     WHERE j.run_id = %s AND j.judgment_id = ANY(%s)
                       AND v.requirement_id = j.requirement_id"""),
        ("MISMATCH", """SELECT s.judgment_id FROM output_item_source s
                        JOIN output_item o USING (item_id)
                        WHERE o.run_id = %s AND s.judgment_id = ANY(%s)
                          AND o.status <> 'REMOVED' AND o.number_check = 'MISMATCH'"""),
        ("NO_VALUE", """SELECT judgment_id FROM judgment
                        WHERE run_id = %s AND judgment_id = ANY(%s)
                          AND result IN ('NEEDS_REVIEW', 'WARRANTY_TO_FILL')
                          AND coalesce(trim(product_value_raw), '') = ''"""),
    ):
        for (judgment_id,) in conn.execute(sql, (run_id, ids)):
            found.setdefault(judgment_id, reason)
    return found


def act(ctx: RunContext, run_id: int, target: str, target_id: int, action: str,
        value: dict | None = None, reason: str | None = None,
        actor_id: int | None = None) -> dict:
    """후보 하나에 확정·수정·반려(제안 포인트는 채택·버림·수정)를 남긴다.

    판정이나 위험 조건을 바꾸면 보증값·목록·제안 포인트를 다시 만들고 누락 점검을 다시 한다.
    """
    conn = ctx.conn
    if action not in ACTIONS.get(target, set()):
        raise ReviewError(400, f"{target}에는 {action} 동작이 없습니다.")
    if action in NEEDS_REASON and not (reason or "").strip():
        raise ReviewError(400, "수정·반려·버림에는 사유가 필요합니다.")
    require_stage(conn, run_id, "ENGINEER_REVIEW")
    actor_id = actor_id or default_user(conn, "ENGINEER")
    _user_role(conn, actor_id)
    before = row(conn, target, target_id, run_id)
    if target == "judgment" and not before["is_current"]:
        raise ReviewError(409, "현재 판정이 아닙니다 (비교 제품을 바꾸기 전 판정).")
    if action in QUERY_ACTIONS:
        if _user_role(conn, actor_id) != "ENGINEER":
            raise ReviewError(403, "질의 보냄은 검토 엔지니어만 표시할 수 있습니다.")
        _apply(conn, target, before, action, {"actor_id": actor_id})
        after = row(conn, target, target_id, run_id)
        log(conn, run_id, target, target_id, action, before, after, reason, actor_id)
        conn.commit()
        return {"before": _json(before).obj, "after": _json(after).obj,
                "submission_check": _latest_check(conn, run_id)}
    _apply(conn, target, before, action, value or {})
    if target == "judgment" and action == "EDIT":
        conn.execute("UPDATE judgment SET reason_text = %s WHERE judgment_id = %s",
                     (f"엔지니어 수정: {reason.strip()}", target_id))
    after = row(conn, target, target_id, run_id)
    log(conn, run_id, target, target_id, action, before, after, reason, actor_id)
    conn.commit()
    if target in ("judgment", "risk_flag"):
        ids = readable_documents(conn, [r[0] for r in conn.execute(
            "SELECT document_id FROM run_document WHERE run_id = %s", (run_id,))])
        if target == "judgment":
            build_warranty(conn, run_id)
        build_outputs(conn, run_id, ids, ctx.llm)
        build_proposals(conn, run_id, ctx.llm)
        conn.commit()
    elif target == "output_item":
        check_submission(conn, run_id)
    build_assignments(conn, run_id)                 # 채택한 제안 포인트는 영업·견적에 전달 (FR-11)
    conn.commit()
    send_after_confirm(conn, run_id, actor_id, ctx.llm)      # 확인을 마친 요청은 부서로 메일
    return {"before": _json(before).obj, "after": _json(after).obj,
            "submission_check": _latest_check(conn, run_id)}


def _latest_check(conn: psycopg.Connection, run_id: int) -> dict | None:
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute(
            "SELECT deviation_candidates, deviation_listed, missing_judgment_ids, open_queries, "
            "ar_codes FROM submission_check WHERE run_id = %s ORDER BY check_id DESC LIMIT 1",
            (run_id,)).fetchone()
    return row


# 제품표에 연결되지 않은 항목의 보증값 빈칸: 입찰자가 원래 써 넣는 칸이라 의심할 줄이 아니다
# (AR-03 안 1, update-review-ratio-hand-fill)
HAND_FILL = "(w.status = 'EMPTY_REVIEW' AND w.reason_code = 'NOT_MAPPED')"


def review_ratio(conn: psycopg.Connection, run_id: int) -> dict:
    """"확인 필요" 비율 (AR-03): 보증값 후보를 채운 칸, 직접 작성할 칸,
    엔지니어가 확정·수정한 것은 뺀다.

    직접 작성할 칸 수(hand_fill)는 따로 돌려준다.
    """
    review, total, hand_fill = conn.execute(
        f"""SELECT count(*) FILTER (WHERE j.review_status = 'CANDIDATE' AND (
                      j.result = 'NEEDS_REVIEW' OR w.status = 'EMPTY_REVIEW')
                      AND NOT COALESCE({HAND_FILL}, FALSE)),
                  count(*) FILTER (WHERE w.status IS DISTINCT FROM 'CANDIDATE'
                                     AND w.status IS DISTINCT FROM 'CONFIRMED'
                                     AND NOT COALESCE({HAND_FILL}, FALSE)),
                  count(*) FILTER (WHERE COALESCE({HAND_FILL}, FALSE))
           FROM judgment j
           LEFT JOIN warranty_candidate w ON w.judgment_id = j.judgment_id
           WHERE j.run_id = %s AND j.is_current AND j.review_status <> 'REJECTED'""",
        (run_id,)).fetchone()
    threshold = float(conn.execute(
        "SELECT threshold FROM approval_rule WHERE ar_code = 'AR-03'").fetchone()[0])
    return {"review": review, "total": total, "threshold": threshold, "hand_fill": hand_fill}


def criteria(conn: psycopg.Connection, run_id: int) -> list[Criterion]:
    """승인 기준 판단 (코드만, CR-01). 걸린 기준과 사람이 읽는 내용."""
    out: list[Criterion] = []
    deviations = conn.execute(
        "SELECT count(*) FROM judgment WHERE run_id = %s AND is_current "
        "AND review_status <> 'REJECTED' AND result = 'DEVIATION_CANDIDATE'",
        (run_id,)).fetchone()[0]
    if deviations:
        out.append(Criterion("AR-01", f"일탈 후보 {deviations}건"))
    blanket = conn.execute(
        "SELECT count(*) FROM risk_flag WHERE run_id = %s AND risk_kind = 'BLANKET' "
        "AND status <> 'CLOSED_OK'", (run_id,)).fetchone()[0]
    if blanket:
        out.append(Criterion("AR-02", f"포괄 조항 {blanket}건"))
    ratio = review_ratio(conn, run_id)
    review, total, threshold = ratio["review"], ratio["total"], ratio["threshold"]
    if total and review / total > threshold:
        out.append(Criterion("AR-03", f"확인 필요 {review}/{total}건 "
                                      f"({review / total:.0%}, 기준 {threshold:.0%})"))
    mismatch = conn.execute(
        "SELECT count(*) FROM risk_flag WHERE run_id = %s AND risk_kind = 'VALUE_MISMATCH' "
        "AND status <> 'CLOSED_OK'", (run_id,)).fetchone()[0]
    queries = conn.execute(
        "SELECT count(*) FROM output_item WHERE run_id = %s AND list_kind = 'QUERY' "
        "AND status <> 'REMOVED'", (run_id,)).fetchone()[0]
    if mismatch or queries:
        out.append(Criterion("AR-06", f"값 불일치 {mismatch}건, 질의 {queries}건"))
    check = check_submission(conn, run_id)
    if check["missing_judgment_ids"]:
        out.append(Criterion("AR-07", f"목록에 없는 일탈 {len(check['missing_judgment_ids'])}건"))
    adopted = conn.execute(
        "SELECT count(*) FROM proposal_point WHERE run_id = %s AND status = ANY(%s)",
        (run_id, list(DELIVERED_POINTS))).fetchone()[0]
    if adopted:
        out.append(Criterion("AR-08", f"전달할 제안 포인트 {adopted}건 (채택한 것만)"))
    return out


def finish_review(conn: psycopg.Connection, run_id: int, approver_id: int | None,
                  comment: str | None, actor_id: int | None = None) -> dict:
    """결재 상신. 걸린 기준을 기록하고, 걸린 것이 없어도 승인 대기로 둔다 [결정 2026-10-28]."""
    require_stage(conn, run_id, "ENGINEER_REVIEW")
    comment = (comment or "").strip()
    if not comment:
        raise ReviewError(400, "상신 의견이 필요합니다.")
    if approver_id is None:
        raise ReviewError(400, "결재자를 골라 주세요.")
    actor_id = actor_id or default_user(conn, "ENGINEER")
    if _user_role(conn, actor_id) != "ENGINEER":
        raise ReviewError(403, "결재 상신은 기술 검토 엔지니어만 할 수 있습니다.")
    if _user_role(conn, approver_id, 404) != "APPROVER":
        raise ReviewError(400, "결재자는 승인자만 될 수 있습니다.")
    found = criteria(conn, run_id)
    with conn.transaction():
        approval_id = conn.execute(
            """INSERT INTO approval (run_id, approver_id, requested_by, request_comment)
               VALUES (%s, %s, %s, %s) RETURNING approval_id""",
            (run_id, approver_id, actor_id, comment)).fetchone()[0]
        for c in found:
            conn.execute("INSERT INTO approval_reason VALUES (%s, %s, %s)",
                         (approval_id, c.ar_code, c.detail))
        conn.execute(
            "UPDATE review_run SET stage = 'APPROVAL', graph_state = graph_state || %s "
            "WHERE run_id = %s", (Jsonb({"step": "approval"}), run_id))
        log(conn, run_id, "review_run", run_id, "CONFIRM", {"stage": "ENGINEER_REVIEW"},
            {"stage": "APPROVAL", "approver_id": approver_id,
             "ar_codes": [c.ar_code for c in found]}, comment, actor_id)
        graph_flow.advance(conn, run_id, "submit")
    return {"stage": "APPROVAL", "approval_id": approval_id,
            "criteria": [{"ar_code": c.ar_code, "detail": c.detail} for c in found]}


def _open_request(conn: psycopg.Connection, run_id: int) -> tuple[int, int | None]:
    """결정 전인 가장 최근 상신 (approval_id, 지정 결재자)."""
    found = conn.execute(
        "SELECT approval_id, approver_id FROM approval WHERE run_id = %s AND decision IS NULL "
        "ORDER BY approval_id DESC LIMIT 1", (run_id,)).fetchone()
    if found is None:
        raise ReviewError(409, "결정 전인 상신이 없습니다.")
    return found[0], found[1]


def decide(conn: psycopg.Connection, run_id: int, decision: str, comment: str | None,
           actor_id: int | None = None) -> dict:
    """지정된 결재자가 승인 또는 반려한다. 결정 전에는 승인됨으로 바뀌지 않는다."""
    if decision not in ("APPROVED", "REJECTED"):
        raise ReviewError(400, "결정은 APPROVED 또는 REJECTED입니다.")
    if decision == "REJECTED" and not (comment or "").strip():
        raise ReviewError(400, "반려에는 의견이 필요합니다.")
    require_stage(conn, run_id, "APPROVAL")
    approval_id, approver_id = _open_request(conn, run_id)
    actor_id = actor_id or approver_id or default_user(conn, "APPROVER")
    if _user_role(conn, actor_id) != "APPROVER":
        raise ReviewError(403, "승인자만 승인·반려할 수 있습니다.")
    if approver_id is not None and actor_id != approver_id:
        raise ReviewError(403, "지정된 결재자만 결정할 수 있습니다.")
    with conn.transaction():
        conn.execute(
            """UPDATE approval SET decision = %s, comment = %s, approver_id = %s,
                      decided_at = now() WHERE approval_id = %s""",
            (decision, comment, actor_id, approval_id))
        conn.execute(
            "UPDATE review_run SET stage = %s, graph_state = graph_state || %s "
            "WHERE run_id = %s", (decision, Jsonb({"step": decision.lower()}), run_id))
        log(conn, run_id, "review_run", run_id,
            "CONFIRM" if decision == "APPROVED" else "REJECT", {"stage": "APPROVAL"},
            {"stage": decision}, comment, actor_id)
        graph_flow.advance(conn, run_id, "approve" if decision == "APPROVED" else "reject")
    return approval(conn, run_id) | {"approval_id": approval_id}


def withdraw(conn: psycopg.Connection, run_id: int, actor_id: int | None = None) -> dict:
    """결정 전인 상신을 취소하고 담당자 확인으로 되돌린다."""
    require_stage(conn, run_id, "APPROVAL")
    actor_id = actor_id or default_user(conn, "ENGINEER")
    if _user_role(conn, actor_id) != "ENGINEER":
        raise ReviewError(403, "상신 취소는 기술 검토 엔지니어만 할 수 있습니다.")
    approval_id, _ = _open_request(conn, run_id)
    with conn.transaction():
        conn.execute("UPDATE approval SET decision = 'WITHDRAWN', withdrawn_at = now() "
                     "WHERE approval_id = %s", (approval_id,))
        conn.execute("UPDATE review_run SET stage = 'ENGINEER_REVIEW', graph_state = "
                     "graph_state || %s WHERE run_id = %s",
                     (Jsonb({"step": "engineer_review"}), run_id))
        log(conn, run_id, "review_run", run_id, "EDIT", {"stage": "APPROVAL"},
            {"stage": "ENGINEER_REVIEW"}, "상신 취소", actor_id)
        graph_flow.advance(conn, run_id, "withdraw")
    return {"stage": "ENGINEER_REVIEW", "approval_id": approval_id}


def reopen(conn: psycopg.Connection, run_id: int, actor_id: int | None = None) -> dict:
    """반려된 실행을 담당자 확인으로 되돌려 고친 뒤 다시 올린다."""
    require_stage(conn, run_id, "REJECTED")
    actor_id = actor_id or default_user(conn, "ENGINEER")
    with conn.transaction():
        conn.execute("UPDATE review_run SET stage = 'ENGINEER_REVIEW', graph_state = "
                     "graph_state || %s WHERE run_id = %s",
                     (Jsonb({"step": "engineer_review"}), run_id))
        log(conn, run_id, "review_run", run_id, "EDIT", {"stage": "REJECTED"},
            {"stage": "ENGINEER_REVIEW"}, "반려 뒤 다시 확인", actor_id)
        graph_flow.advance(conn, run_id, "reopen")
    return {"stage": "ENGINEER_REVIEW"}


def approval(conn: psycopg.Connection, run_id: int) -> dict:
    """승인 화면: 상신 정보, 걸린 기준, 누락 점검, 결정. 취소한 상신은 보이지 않는다."""
    stage = _stage(conn, run_id)
    with conn.cursor(row_factory=dict_row) as cur:
        latest = cur.execute(
            """SELECT a.approval_id, a.decision, a.comment, a.requested_at, a.decided_at,
                      a.approver_id, u.user_name AS approver, a.requested_by AS requested_by_id,
                      q.user_name AS requested_by, a.request_comment
               FROM approval a LEFT JOIN app_user u ON u.user_id = a.approver_id
               LEFT JOIN app_user q ON q.user_id = a.requested_by
               WHERE a.run_id = %s AND a.decision IS DISTINCT FROM 'WITHDRAWN'
               ORDER BY a.approval_id DESC LIMIT 1""",
            (run_id,)).fetchone()
        reasons = cur.execute(
            """SELECT r.ar_code, r.detail, ar.description FROM approval_reason r
               JOIN approval_rule ar USING (ar_code) WHERE r.approval_id = %s
               ORDER BY r.ar_code""", (latest["approval_id"],)).fetchall() if latest else []
    preview = [{"ar_code": c.ar_code, "detail": c.detail}
               for c in criteria(conn, run_id)] if stage == "ENGINEER_REVIEW" else None
    ratio = review_ratio(conn, run_id)
    conn.commit()
    return {"stage": stage, "approval": latest, "reasons": reasons, "preview": preview,
            "review_ratio": ratio, "submission_check": _latest_check(conn, run_id)}


TYPE_EDITORS = ("ENGINEER", "APPROVER")
NO_TYPE = "NONE"


def set_type(conn: psycopg.Connection, run_id: int, requirement_id: int, type_code: str,
             reason: str | None, actor_id: int) -> dict:
    """사람이 주 유형을 고친다 (add-type-examples, C3). 근거 HUMAN, 이력, 담당 전달 다시 만듦.

    NONE은 미분류(주 유형 태그 없음). 보조 유형은 그대로 둔다(고친 유형과 같으면 지움).
    """
    if _user_role(conn, actor_id) not in TYPE_EDITORS:
        raise ReviewError(403, "유형은 기술 검토 엔지니어와 승인자만 고칠 수 있습니다.")
    found = conn.execute(
        "SELECT 1 FROM requirement q JOIN run_document rd USING (document_id) "
        "WHERE rd.run_id = %s AND q.requirement_id = %s", (run_id, requirement_id)).fetchone()
    if found is None:
        raise ReviewError(404, f"이 검토에 요구사항 {requirement_id}이(가) 없습니다.")
    if type_code != NO_TYPE and conn.execute(
            "SELECT 1 FROM requirement_type WHERE type_code = %s", (type_code,)).fetchone() is None:
        raise ReviewError(400, f"알 수 없는 유형입니다: {type_code}")
    old = conn.execute("SELECT type_code, decided_by FROM requirement_type_tag "
                       "WHERE requirement_id = %s AND is_primary", (requirement_id,)).fetchone()
    before = {"type_code": old[0] if old else NO_TYPE, "decided_by": old[1] if old else None}
    after = {"type_code": type_code, "decided_by": "HUMAN"}
    conn.execute("DELETE FROM requirement_type_tag WHERE requirement_id = %s "
                 "AND (is_primary OR type_code = %s)", (requirement_id, type_code))
    if type_code != NO_TYPE:
        conn.execute("INSERT INTO requirement_type_tag (requirement_id, type_code, is_primary, "
                     "decided_by) VALUES (%s, %s, TRUE, 'HUMAN')", (requirement_id, type_code))
    log(conn, run_id, "requirement", requirement_id, "EDIT", before, after, reason,
        actor_id)
    conn.commit()
    build_assignments(conn, run_id)       # 유형이 바뀌면 담당 부서가 바뀐다 (FR-11)
    conn.commit()
    return {"requirement_id": requirement_id, "before": before["type_code"],
            "after": type_code}


def history(conn: psycopg.Connection, run_id: int, target: str | None = None,
            target_id: int | None = None) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            """SELECT l.log_id, l.target_table, l.target_id, l.action, l.before_value,
                      l.after_value, l.reason, u.user_name AS actor, l.acted_at
               FROM review_log l JOIN app_user u ON u.user_id = l.actor_id
               WHERE l.run_id = %s AND (%s::text IS NULL OR l.target_table = %s)
                 AND (%s::int IS NULL OR l.target_id = %s)
               ORDER BY l.log_id""", (run_id, target, target, target_id, target_id)).fetchall()
    labels = _target_labels(conn, rows)
    for r in rows:
        r["target_label"] = labels.get((r["target_table"], r["target_id"]))
    return rows


# 이력 탭 문장에 쓰는 대상 이름 (항목 이름, 위험 표현, 근거 등). 대상 표마다 한 번에 찾는다.
LABEL_SQL = {
    "judgment": """
        SELECT j.judgment_id, COALESCE(k.name_ko, tr.item_name_raw, left(q.text_raw, 40))
        FROM judgment j JOIN requirement q USING (requirement_id)
        LEFT JOIN table_row tr ON tr.row_id = q.row_id
        LEFT JOIN req_value v ON v.value_id = j.value_id
        LEFT JOIN item_key k ON k.item_key = v.item_key
        WHERE j.judgment_id = ANY(%s)""",
    "warranty_candidate": """
        SELECT w.candidate_id, COALESCE(k.name_ko, tr.item_name_raw, left(q.text_raw, 40))
        FROM warranty_candidate w JOIN judgment j USING (judgment_id)
        JOIN requirement q ON q.requirement_id = j.requirement_id
        LEFT JOIN table_row tr ON tr.row_id = q.row_id
        LEFT JOIN req_value v ON v.value_id = j.value_id
        LEFT JOIN item_key k ON k.item_key = v.item_key
        WHERE w.candidate_id = ANY(%s)""",
    "risk_flag": """
        SELECT f.risk_id, COALESCE(e.expression, k.name_ko, f.item_key)
        FROM risk_flag f LEFT JOIN risk_expression e USING (expr_id)
        LEFT JOIN item_key k ON k.item_key = f.item_key
        WHERE f.risk_id = ANY(%s)""",
    "output_item": "SELECT item_id, left(text_draft, 40) FROM output_item WHERE item_id = ANY(%s)",
    "proposal_point": "SELECT point_id, basis FROM proposal_point WHERE point_id = ANY(%s)",
    "requirement": """SELECT requirement_id, left(text_raw, 40) FROM requirement
                      WHERE requirement_id = ANY(%s)""",
    "loss_calc": "SELECT loss_calc_id, product_code FROM loss_calc WHERE loss_calc_id = ANY(%s)",
    "read_check": "SELECT read_check_id, label FROM read_check WHERE read_check_id = ANY(%s)",
}


def _target_labels(conn: psycopg.Connection, rows: list[dict]) -> dict[tuple[str, int], str]:
    ids: dict[str, set[int]] = {}
    for r in rows:
        if r["target_table"] in LABEL_SQL:
            ids.setdefault(r["target_table"], set()).add(r["target_id"])
    out = {}
    for table, wanted in ids.items():
        for target_id, label in conn.execute(LABEL_SQL[table], (list(wanted),)):
            if label:
                out[(table, target_id)] = label
    return out


def deliverables(conn: psycopg.Connection, run_id: int) -> dict:
    """전달 대상: 빼지 않은 일탈·질의 목록, 확정한 보증값, 채택한 제안 포인트만 (AR-08)."""
    with conn.cursor(row_factory=dict_row) as cur:
        points = cur.execute(
            "SELECT point_id, point_kind, text_draft, basis, is_assumed, status "
            "FROM proposal_point WHERE run_id = %s AND status = ANY(%s) ORDER BY point_id",
            (run_id, list(DELIVERED_POINTS))).fetchall()
        items = cur.execute(
            "SELECT item_id, list_kind, list_name, text_draft, status, is_assumed "
            "FROM output_item WHERE run_id = %s AND status <> 'REMOVED' "
            "ORDER BY list_kind, item_id", (run_id,)).fetchall()
        warranty = cur.execute(
            "SELECT w.candidate_id, w.judgment_id, w.candidate_value, w.candidate_unit, "
            "w.source_kind FROM warranty_candidate w WHERE w.run_id = %s "
            "AND w.status = 'CONFIRMED' ORDER BY w.candidate_id", (run_id,)).fetchall()
    return {"proposals": points, "outputs": items, "warranty": warranty}


# ---------------------------------------------------------------- 내 할 일 (FR-11)

TASK_STATUSES = ("TODO", "DOING", "DONE")
VISIBLE_STAGES = ("ENGINEER_REVIEW", "APPROVAL", "APPROVED", "REJECTED")


def set_assignment_status(conn: psycopg.Connection, assignment_id: int, status: str,
                          actor_id: int, reply_note: str | None = None) -> dict:
    """엔지니어가 회신 받음을 기록하거나 되돌린다 (메일 보냄 ↔ 회신 받음).

    메일 보냄은 발송에 성공할 때 시스템이 기록하고, 견적·품질·영업 담당은 상태를 바꾸지 않는다.
    """
    if status not in TASK_STATUSES:
        raise ReviewError(400, f"상태 {status}은(는) 없습니다.")
    found = conn.execute("SELECT run_id, status FROM assignment WHERE assignment_id = %s",
                         (assignment_id,)).fetchone()
    if found is None:
        raise ReviewError(404, f"할 일 {assignment_id}이(가) 없습니다.")
    if _user_role(conn, actor_id) != "ENGINEER":
        raise ReviewError(403, "회신 기록은 기술 검토 엔지니어만 할 수 있습니다.")
    run_id, current = found
    if {current, status} != {"DOING", "DONE"}:
        raise ReviewError(409, "메일을 보낸 요청만 회신 받음으로 표시하거나 되돌릴 수 있습니다.")
    note = (reply_note or "").strip() or None
    if status == "DONE":
        conn.execute("UPDATE assignment SET status = 'DONE', replied_at = now(), replied_by = %s, "
                     "reply_note = %s, updated_at = now() WHERE assignment_id = %s",
                     (actor_id, note, assignment_id))
    else:
        conn.execute("UPDATE assignment SET status = 'DOING', replied_at = NULL, "
                     "replied_by = NULL, reply_note = NULL, updated_at = now() "
                     "WHERE assignment_id = %s", (assignment_id,))
    log(conn, run_id, "assignment", assignment_id, "REPLY" if status == "DONE" else "UNDO",
        {"status": current}, {"status": status, "reply_note": note}, None, actor_id)
    conn.commit()
    return {"assignment_id": assignment_id, "status": status}


def _review_cards(conn: psycopg.Connection, stage: str,
                  approver_id: int | None = None) -> list[dict]:
    """엔지니어는 담당자 확인, 승인자는 자기에게 상신된 승인 대기 검토. 걸린 승인 기준을 붙인다."""
    cards = []
    for run in queries.run_list(conn, 200):
        if run["stage"] != stage:
            continue
        if stage == "ENGINEER_REVIEW":
            found = [{"ar_code": c.ar_code, "detail": c.detail}
                     for c in criteria(conn, run["run_id"])]
            extra = {}
        else:
            screen = approval(conn, run["run_id"])
            if (screen["approval"] or {}).get("approver_id") != approver_id:
                continue                        # 다른 결재자에게 간 검토는 보이지 않는다
            found = screen["reasons"]
            extra = {"approval": screen["approval"]}
        summary = queries.run_summary(conn, run["run_id"])
        cards.append({**run, "summary": summary, "criteria": found, **extra})
    conn.commit()
    return cards


DEPT_ROLES = ("COST", "QUALITY", "SALES")


def assignments_for(conn: psycopg.Connection, role: str | None,
                    run_id: int | None = None) -> list[dict]:
    """한 부서(role)의 협조 요청. role이 None이면 세 부서 모두 (협조 요청 화면 탭 건수)."""
    roles = list(DEPT_ROLES) if role is None else [role]
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            f"""SELECT a.assignment_id, a.run_id, a.assignee_role, a.status, a.repeat_count,
                      a.sent_at, a.updated_at, a.requirement_id, a.requirement_ids, a.point_id,
                      a.type_code, t.type_name, u.user_name AS assignee,
                      a.mail_sent_at, a.mail_to, a.mail_error, su.user_name AS sent_by_name,
                      a.replied_at, ru.user_name AS replied_by_name, a.reply_note,
                      a.ask_text, a.ask_by,
                      COALESCE(q.text_raw, p.text_draft) AS text, p.point_kind,
                      p.requirement_id AS point_requirement_id, p.is_assumed, r.stage,
                      {queries.REVIEW_INFO}
               FROM assignment a JOIN review_run r ON r.run_id = a.run_id
               LEFT JOIN requirement_type t ON t.type_code = a.type_code
               LEFT JOIN app_user u ON u.user_id = a.assignee_id
               LEFT JOIN app_user su ON su.user_id = a.sent_by
               LEFT JOIN app_user ru ON ru.user_id = a.replied_by
               LEFT JOIN requirement q ON q.requirement_id = a.requirement_id
               LEFT JOIN proposal_point p ON p.point_id = a.point_id
               WHERE a.assignee_role = ANY(%s) AND r.stage = ANY(%s)
                 AND (a.requirement_id IS NOT NULL OR a.point_id IS NOT NULL)
                 AND (%s::int IS NULL OR a.run_id = %s)
               ORDER BY a.run_id DESC, a.point_id IS NULL, a.assignment_id""",
            (roles, list(VISIBLE_STAGES), run_id, run_id)).fetchall()
        files = {(f["run_id"], f["file_no"]): f["file_name"] for f in cur.execute(
            """SELECT rd.run_id, d.file_no, d.file_name FROM run_document rd
               JOIN document d USING (document_id) WHERE rd.run_id = ANY(%s)""",
            (list({r["run_id"] for r in rows}),))}
    mailer = get_mailer()
    out = []
    for r in rows:
        ids = r["requirement_ids"] or [r["point_requirement_id"]]
        locations = queries._locations(conn, ids, r["run_id"])
        r["locations"] = [loc for i in ids for loc in locations.get(i, [])]
        r["file_name"] = files.get((r["run_id"], r["locations"][0]["file_no"])) \
            if r["locations"] else None
        r["requirement_id"] = r["requirement_id"] or r["point_requirement_id"]
        r["dept_address"] = mailer.address(r["assignee_role"])
        if r["locations"]:                      # 원문 위치가 없으면 보내지 않는다 (CR-02)
            out.append(r)
    return out


def my_tasks(conn: psycopg.Connection, user_id: int) -> dict:
    """고른 사용자 역할의 "내 할 일". 엔지니어·승인자는 멈춰 있는 검토, 담당자는 전달받은 할 일."""
    role = _user_role(conn, user_id)
    out: dict = {"role": role, "reviews": [], "assignments": []}
    if role == "ENGINEER":
        out["reviews"] = _review_cards(conn, "ENGINEER_REVIEW")
    elif role == "APPROVER":
        out["reviews"] = _review_cards(conn, "APPROVAL", user_id)
    else:
        out["assignments"] = assignments_for(conn, role)
    return out
