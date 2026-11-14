"""검토에 문서 더하기와 사람 확인 이어받기 (change add-document-addendum, FR-01 ⑤, FR-10 ⑤).

분석을 마친 검토(담당자 확인 단계)에 정정본·추가 문서(Addendum)를 더하면 처음 파일과 함께
같은 검토를 처음부터 다시 돌린다. 처리한 문서는 같은 처리 열쇠로 다시 쓰이므로(AI 다시 부르지 않음)
요구사항·값 id가 그대로다. 그래서 "같은 줄"은 (요구사항, 값, 비교 제품, 비교 규칙)이 같은 판정이다.

이어받기는 실행 흐름의 판정·위험 조건 단계에서 늘 한다. 사람이 손대지 않은 검토에서는 할 일이 없고,
문서 추가가 실패해 다시 시도할 때도 같은 규칙으로 이어받는다.
"""

from pathlib import Path

import psycopg
from psycopg.types.json import Json

JUDGMENT_KEY = ("requirement_id", "value_id", "product_code", "compare_rule_id")
EDITED_COLUMNS = ("result", "reason_code", "reason_text", "margin_value", "margin_kind",
                  "margin_direction")


def prepare_add(conn: psycopg.Connection, run_id: int, new_paths: list[Path],
                new_choices: dict[str, dict],
                actor_id: int | None) -> tuple[list[Path], dict[str, dict]]:
    """검토를 다시 처리 중으로 돌리고 (처음 파일 + 더한 파일, 합친 분류)를 돌려준다.

    엔지니어만 더할 수 있다(검토 담당이 아닌 승인자·협조 부서는 403).
    """
    from rfp_agent.pipeline.review import ReviewError, log  # review가 run을 불러 순환을 피함

    if actor_id is None:
        actor_id = conn.execute("SELECT min(user_id) FROM app_user WHERE role = 'ENGINEER'"
                                ).fetchone()[0]
    role = conn.execute("SELECT role FROM app_user WHERE user_id = %s", (actor_id,)).fetchone()
    if role is None:
        raise ReviewError(400, f"사용자 {actor_id}이(가) 없습니다.")
    if role[0] != "ENGINEER":
        raise ReviewError(403, "문서는 검토 엔지니어만 더할 수 있습니다.")
    with conn.transaction():
        row = conn.execute("SELECT stage, graph_state->'inputs' FROM review_run "
                           "WHERE run_id = %s FOR UPDATE", (run_id,)).fetchone()
        if row is None:
            raise ReviewError(404, f"검토 실행 {run_id}이(가) 없습니다.")
        stage, inputs = row
        if stage != "ENGINEER_REVIEW":
            raise ReviewError(409, "문서는 담당자 확인 단계(결재 상신 전)에서만 더할 수 있습니다.")
        if not inputs or not inputs.get("paths"):
            raise ReviewError(409, "이 검토는 처음 올린 파일 정보가 없어 문서를 더할 수 없습니다. "
                                   "검토를 다시 등록해 주세요.")
        paths = [Path(p) for p in inputs["paths"]]
        missing = [p.name for p in paths if not p.exists()]
        if missing:
            raise ReviewError(409, f"처음 올린 파일을 찾을 수 없습니다({', '.join(missing)}). "
                                   "검토를 다시 등록해 주세요.")
        if not new_paths:
            raise ReviewError(400, "더할 docx·PDF 파일을 하나 이상 골라 주세요.")
        names = {p.name for p in paths}
        same = [p.name for p in new_paths if p in paths or p.name in names]
        if same:
            raise ReviewError(409, f"이미 이 검토에 있는 파일입니다: {', '.join(same)}. "
                                   "정정본은 파일 이름을 바꿔 올려 주세요.")
        choices = {**(inputs.get("choices") or {}), **new_choices}
        conn.execute(
            """UPDATE review_run SET stage = 'PROCESSING', failed_step = NULL,
                      error_message = NULL, finished_at = NULL,
                      cancel_requested_at = NULL, cancel_requested_by = NULL,
                      graph_state = graph_state || jsonb_build_object(
                          'step', 'created', 'detail', NULL, 'updated_at', now(),
                          'added_by', %s::int,
                          'revision_pending', jsonb_build_object('files', %s::jsonb))
               WHERE run_id = %s""", (actor_id, Json([p.name for p in new_paths]), run_id))
        log(conn, run_id, "run_document", run_id, "ADD", None,
            {"files": [p.name for p in new_paths]}, None, actor_id)
    return paths + new_paths, choices


def prepare_rewind(conn: psycopg.Connection, run_id: int, step: str, reason: str,
                   actor_id: int | None) -> tuple[list[Path], dict[str, dict]]:
    """단계부터 다시 처리 요청을 검사하고 검토를 처리 중으로 돌린다 (add-step-rewind, C2).

    엔지니어만, 담당자 확인 단계에서 흐름이 그 자리에 멈춰 있을 때만. 사람 확정은 다시 도는
    판정·위험 조건 단계가 같은 줄로 이어받는다. (처음 파일, 분류)를 돌려준다.
    """
    from rfp_agent.pipeline import graph_flow
    from rfp_agent.pipeline.review import ReviewError, log
    from rfp_agent.pipeline.run import PIPELINE

    if actor_id is None:
        actor_id = conn.execute("SELECT min(user_id) FROM app_user WHERE role = 'ENGINEER'"
                                ).fetchone()[0]
    role = conn.execute("SELECT role FROM app_user WHERE user_id = %s", (actor_id,)).fetchone()
    if role is None:
        raise ReviewError(400, f"사용자 {actor_id}이(가) 없습니다.")
    if role[0] != "ENGINEER":
        raise ReviewError(403, "단계부터 다시 처리는 검토 엔지니어만 할 수 있습니다.")
    if step not in PIPELINE:
        raise ReviewError(400, f"처리 단계가 아닙니다: {step}")
    if not (reason or "").strip():
        raise ReviewError(400, "다시 처리하는 사유를 적어 주세요.")
    with conn.transaction():
        row = conn.execute("SELECT stage, graph_state->'inputs' FROM review_run "
                           "WHERE run_id = %s FOR UPDATE", (run_id,)).fetchone()
        if row is None:
            raise ReviewError(404, f"검토 실행 {run_id}이(가) 없습니다.")
        stage, inputs = row
        if stage != "ENGINEER_REVIEW":
            raise ReviewError(409, "단계부터 다시 처리는 담당자 확인 단계(결재 상신 전)에서만 "
                                   "할 수 있습니다. 상신했으면 상신 취소부터 해 주세요.")
        if graph_flow.history(conn, run_id)["stop"] != "engineer_review":
            raise ReviewError(409, "이 검토는 흐름 기록이 없어 단계부터 다시 처리할 수 없습니다.")
        if not inputs or not inputs.get("paths"):
            raise ReviewError(409, "이 검토는 처음 올린 파일 정보가 없어 다시 처리할 수 없습니다.")
        paths = [Path(p) for p in inputs["paths"]]
        missing = [p.name for p in paths if not p.exists()]
        if missing:
            raise ReviewError(409, f"처음 올린 파일을 찾을 수 없습니다({', '.join(missing)}).")
        conn.execute(
            """UPDATE review_run SET stage = 'PROCESSING', finished_at = NULL,
                      graph_state = graph_state || jsonb_build_object(
                          'step', 'created', 'detail', NULL, 'updated_at', now())
               WHERE run_id = %s""", (run_id,))
        log(conn, run_id, "review_run", run_id, "REWIND", None, {"step": step}, reason.strip(),
            actor_id)
    return paths, inputs.get("choices") or {}


def current_judgments(conn: psycopg.Connection, run_id: int) -> list[int]:
    """다시 판정하기 전 지금 판정 줄. 이 줄의 확인 상태만 옮긴다(바꿔 보기 전 제품 줄은 아님)."""
    return [r[0] for r in conn.execute(
        "SELECT judgment_id FROM judgment WHERE run_id = %s AND is_current", (run_id,))]


def carry_judgments(conn: psycopg.Connection, run_id: int, old_ids: list[int]) -> int:
    """새 판정 줄에 같은 줄(old_ids 가운데)의 확인 상태를 옮긴다.

    확정·반려는 상태만, 수정은 엔지니어가 바꾼 판정 값까지 옮긴다.
    보증값 후보는 새 판정 줄로 다시 잇는다
    (확정·반려한 보증값은 다음 보증값 단계가 판정 줄 기준으로 그대로 둔다). 옮긴 줄 수를 돌려준다.
    """
    keys = ", ".join(JUDGMENT_KEY)
    same = " AND ".join(f"n.{k} IS NOT DISTINCT FROM o.{k}" for k in JUDGMENT_KEY)
    pairs = conn.execute(
        f"""WITH o AS (
                SELECT DISTINCT ON ({keys}) * FROM judgment
                WHERE judgment_id = ANY(%(old)s)
                ORDER BY {keys}, judgment_id DESC)
            SELECT o.judgment_id, n.judgment_id, o.review_status
            FROM judgment n JOIN o ON {same}
            WHERE n.run_id = %(run)s AND n.is_current AND NOT n.judgment_id = ANY(%(old)s)""",
        {"run": run_id, "old": old_ids}).fetchall()
    if not pairs:
        return 0
    sets = ", ".join(f"{c} = o.{c}" for c in EDITED_COLUMNS)
    carried = 0
    for old_id, new_id, status in pairs:
        conn.execute("UPDATE warranty_candidate SET judgment_id = %s "
                     "WHERE run_id = %s AND judgment_id = %s", (new_id, run_id, old_id))
        if status == "CANDIDATE":
            continue
        if status == "EDITED":
            conn.execute(f"""UPDATE judgment n SET {sets}, review_status = 'EDITED'
                             FROM judgment o WHERE n.judgment_id = %s AND o.judgment_id = %s""",
                         (new_id, old_id))
        else:
            conn.execute("UPDATE judgment SET review_status = %s WHERE judgment_id = %s",
                         (status, new_id))
        carried += 1
    # 질의 보냄 표시도 같은 줄로 옮긴다 (add-query-sent). 옮긴 뒤 판정이 질의 후보일 때만
    for old_id, new_id, _ in pairs:
        conn.execute("""UPDATE judgment n SET query_sent_at = o.query_sent_at,
                               query_sent_by = o.query_sent_by
                        FROM judgment o WHERE n.judgment_id = %s AND o.judgment_id = %s
                          AND o.query_sent_at IS NOT NULL
                          AND n.result = 'QUERY_CANDIDATE'""", (new_id, old_id))
    return carried


def record_revision(conn: psycopg.Connection, run_id: int, old_ids: list[int]) -> dict | None:
    """문서 추가로 다시 판정했으면 개정 결과를 남긴다 (change add-revision-notice).

    판정 단계에서 이어받기 뒤에 부른다. 문서 추가가 남긴 표시(revision_pending)가 있을 때만
    쓰고 표시를 지운다. 같은 줄(JUDGMENT_KEY)이 이전·새 판정에 다 있고 판정 값이 다르면 "바뀜",
    새 판정에만 있으면 "추가",
    이전 판정에만 있으면 "사라짐". 바뀜·추가 줄 id와 사라짐 수를 graph_state.revision에 둔다.
    """
    row = conn.execute("SELECT graph_state->'revision_pending', graph_state->'revision' "
                       "FROM review_run WHERE run_id = %s", (run_id,)).fetchone()
    if row is None or row[0] is None:
        return None
    pending, last = row
    keys = ", ".join(JUDGMENT_KEY)

    def by_key(where: str, params) -> dict[tuple, tuple[int, str]]:
        return {tuple(r[:4]): (r[4], r[5]) for r in conn.execute(
            f"SELECT {keys}, judgment_id, result FROM judgment WHERE {where} "
            "ORDER BY judgment_id", params)}
    old = by_key("judgment_id = ANY(%s)", (old_ids,))
    new = by_key("run_id = %s AND is_current", (run_id,))
    changed = sorted(jid for k, (jid, result) in new.items() if k in old and old[k][1] != result)
    added = sorted(jid for k, (jid, _) in new.items() if k not in old)
    revision = {
        "no": (last or {}).get("no", 0) + 1,
        "files": pending.get("files") or [],
        "changed": changed, "added": added,
        "removed": sum(1 for k in old if k not in new),
    }
    conn.execute("""UPDATE review_run SET graph_state = (graph_state - 'revision_pending')
                        || jsonb_build_object(
                            'revision', %s::jsonb || jsonb_build_object('at', now()))
                    WHERE run_id = %s""", (Json(revision), run_id))
    return revision


RISK_KEY_SQL = """SELECT f.risk_id, f.risk_kind, f.expr_id, f.item_key,
                         array_agg(m.requirement_id ORDER BY m.requirement_id), f.status
                  FROM risk_flag f JOIN risk_flag_member m USING (risk_id)
                  WHERE f.run_id = %s GROUP BY f.risk_id"""


def risk_snapshot(conn: psycopg.Connection, run_id: int) -> dict[int, tuple]:
    """다시 만들기 전 위험 조건: risk_id → (열쇠, 상태).

    열쇠 = (종류, 표현, 항목, 요구사항 묶음)."""
    return {rid: ((kind, expr, item, tuple(members)), status)
            for rid, kind, expr, item, members, status in conn.execute(RISK_KEY_SQL, (run_id,))}


def risk_statuses(conn: psycopg.Connection, run_id: int) -> dict[tuple, str]:
    """사람이 본(후보가 아닌) 위험 조건의 열쇠 → 상태."""
    return {key: status for key, status in risk_snapshot(conn, run_id).values()
            if status != "CANDIDATE"}


def risk_explanations(conn: psycopg.Connection,
                      old: dict[int, tuple]) -> dict[tuple, tuple[int, str | None, str | None]]:
    """열쇠 → (이전 risk_id, AI 설명, 검증 표시). 같은 후보는 AI에 다시 묻지 않으려고 쓴다."""
    if not old:
        return {}
    rows = {rid: (text, check) for rid, text, check in conn.execute(
        "SELECT risk_id, explanation_ai, explanation_check FROM risk_flag "
        "WHERE risk_id = ANY(%s)", (list(old),))}
    return {key: (rid, *rows.get(rid, (None, None))) for rid, (key, _) in old.items()}


def replace_risks(conn: psycopg.Connection, run_id: int, old: dict[int, tuple]) -> int:
    """새로 만든 위험 조건으로 이전 것(old)을 바꾼다. 옮긴 확인 상태 수를 돌려준다.

    같은 열쇠의 이전 상태를 옮기고, 목록 항목의 출처·묶음 열쇠도 새 위험 조건으로 잇는다
    (그래서 확정한 질의 문장도 다음 목록 단계에서 이어진다). 그 뒤 이전 위험 조건을 지운다.
    """
    by_key = {key: (rid, status) for rid, (key, status) in old.items()}
    carried = 0
    for rid, kind, expr, item, members, _ in conn.execute(RISK_KEY_SQL, (run_id,)).fetchall():
        if rid in old or (hit := by_key.get((kind, expr, item, tuple(members)))) is None:
            continue
        old_id, status = hit
        if status != "CANDIDATE":
            conn.execute("UPDATE risk_flag SET status = %s WHERE risk_id = %s", (status, rid))
            carried += 1
        conn.execute("UPDATE output_item_source SET risk_id = %s WHERE risk_id = %s",
                     (rid, old_id))
        conn.execute("UPDATE output_item SET group_key = %s WHERE run_id = %s AND group_key = %s",
                     (repr(("QUERY", "R", rid)), run_id, repr(("QUERY", "R", old_id))))
    if old:
        ids = list(old)
        conn.execute("DELETE FROM output_item_source WHERE risk_id = ANY(%s)", (ids,))
        conn.execute("DELETE FROM risk_flag_member WHERE risk_id = ANY(%s)", (ids,))
        conn.execute("DELETE FROM risk_flag WHERE risk_id = ANY(%s)", (ids,))
    return carried
