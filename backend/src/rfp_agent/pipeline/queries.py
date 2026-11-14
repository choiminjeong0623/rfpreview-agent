"""검토 실행 결과 조회 (API·CLI 공용). 값은 모두 원문 위치와 함께 낸다 (CR-02)."""

import psycopg
from psycopg.rows import dict_row

from rfp_agent.pipeline.loss import amounts


def _rows(conn: psycopg.Connection, sql: str, params) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


# 실행 요약과 실행 목록이 같이 쓰는 개수 (add-review-info: 목록 개수는 요약과 같아야 한다)
COUNTS = """
               (SELECT count(*) FROM requirement q JOIN run_document rd USING (document_id)
                 WHERE rd.run_id = r.run_id AND q.req_kind = 'REQUIREMENT') AS requirements,
               (SELECT count(*) FROM risk_flag WHERE run_id = r.run_id) AS risks,
               (SELECT count(*) FROM judgment WHERE run_id = r.run_id AND is_current
                  AND result = 'DEVIATION_CANDIDATE') AS deviation_candidates,
               (SELECT count(*) FROM proposal_point WHERE run_id = r.run_id) AS proposals"""

# 사람이 넣은 검토 정보와 검토 번호 RV-<시작 연도>-<실행 번호 세 자리>,
# 연결된 사업 (add-project-status)
REVIEW_INFO = """
               'RV-' || extract(year FROM r.started_at)::int || '-' || lpad(r.run_id::text, 3, '0')
                   AS review_no,
               r.project_name, r.review_name, r.customer_name, r.country, r.due_date,
               r.engineer_id, (SELECT user_name FROM app_user WHERE user_id = r.engineer_id)
                   AS engineer_name,
               r.business_id,
               (SELECT 'PJ-' || extract(year FROM b.created_at)::int || '-'
                       || lpad(b.business_id::text, 3, '0')
                  FROM business b WHERE b.business_id = r.business_id) AS business_no"""


def run_summary(conn: psycopg.Connection, run_id: int) -> dict | None:
    rows = _rows(conn, f"""
        SELECT r.run_id, r.stage, r.dict_version, r.llm_model, r.failed_step, r.error_message,
               r.started_at, r.finished_at, r.graph_state->>'step' AS step,
               r.cancel_requested_at, r.retry_count AS retries,
               (r.stage = 'FAILED' AND r.graph_state ? 'inputs') AS retryable,
               r.graph_state->'detail' AS step_detail,
               COALESCE((r.graph_state->>'updated_at')::timestamptz, r.started_at)
                   AS step_updated_at, {REVIEW_INFO},
               (SELECT count(*) FROM run_document WHERE run_id = r.run_id) AS documents,
               {COUNTS},
               (SELECT count(*) FROM judgment WHERE run_id = r.run_id AND is_current)
                   AS judgments,
               (SELECT count(*) FROM output_item WHERE run_id = r.run_id) AS output_items,
               (SELECT count(*) FROM engineering_check WHERE run_id = r.run_id
                  AND result = 'VIOLATION') AS check_violations,
               r.graph_state->'revision' AS revision
        FROM review_run r WHERE r.run_id = %s""", (run_id,))
    return _with_revision(rows[0]) if rows else None


def _with_revision(row: dict) -> dict:
    """graph_state.revision(줄 id 목록)을 개정 요약(줄 수)으로 바꾼다 (add-revision-notice)."""
    raw = row.get("revision")
    row["revision"] = None if not raw else {
        "no": raw["no"], "at": raw["at"], "files": raw.get("files") or [],
        "changed": len(raw.get("changed") or []), "added": len(raw.get("added") or []),
        "removed": raw.get("removed") or 0}
    return row


def revised_ids(conn: psycopg.Connection, run_id: int) -> dict[int, str]:
    """마지막 개정에서 바뀐(CHANGED)·추가된(ADDED) 판정 줄 id. 개정이 없으면 빈 dict."""
    row = conn.execute("SELECT graph_state->'revision' FROM review_run WHERE run_id = %s",
                       (run_id,)).fetchone()
    raw = (row[0] if row else None) or {}
    return {**{i: "ADDED" for i in raw.get("added") or []},
            **{i: "CHANGED" for i in raw.get("changed") or []}}


def run_documents(conn: psycopg.Connection, run_id: int) -> list[dict]:
    return _rows(conn, """
        SELECT d.document_id, d.file_no, d.file_name, d.bundle, d.doc_kind, d.language,
               d.standard_system, d.judge_target, d.readable, d.classify_by, d.needs_review,
               d.processor, d.process_check, d.reprocessed, d.reprocessed_lines, d.ocr_lines,
               d.line_basis,
               (SELECT count(*) FROM requirement q WHERE q.document_id = d.document_id
                  AND q.req_kind = 'REQUIREMENT') AS requirements
        FROM run_document rd JOIN document d USING (document_id)
        WHERE rd.run_id = %s ORDER BY d.file_no""", (run_id,))


LOCATIONS = """
    SELECT rl.requirement_id, d.file_no, s.section_no, s.title AS section_title,
           t.table_name, tr.item_no, l.line_start, l.line_end,
           line_page(d.page_starts, l.line_start) AS page          -- PDF 쪽 (add-pdf-page-location)
    FROM requirement_location rl
    JOIN source_location l USING (location_id)
    JOIN document d ON d.document_id = l.document_id
    LEFT JOIN section s ON s.section_id = l.section_id
    LEFT JOIN table_row tr ON tr.row_id = l.row_id
    LEFT JOIN doc_table t ON t.table_id = tr.table_id
    WHERE rl.requirement_id = ANY(%s)
      -- 같은 요구가 다른 실행의 문서에도 있으면 그 위치는 빼고 이 실행의 문서 위치만 낸다
      AND (%s::int IS NULL OR l.document_id IN (
            SELECT document_id FROM run_document WHERE run_id = %s))
    ORDER BY d.file_no, l.line_start"""


def _attach(conn: psycopg.Connection, items: list[dict], run_id: int | None = None) -> list[dict]:
    """요구사항마다 원문 위치·유형·값을 붙인다."""
    ids = [i["requirement_id"] for i in items]
    by_id = {i["requirement_id"]: i | {"locations": [], "types": [], "values": []} for i in items}
    for loc in _rows(conn, LOCATIONS, (ids, run_id, run_id)):
        by_id[loc.pop("requirement_id")]["locations"].append(loc)
    for t in _rows(conn, """
            SELECT t.requirement_id, t.type_code, t.is_primary, t.decided_by, tr.rule_code
            FROM requirement_type_tag t LEFT JOIN type_rule tr USING (type_rule_id)
            WHERE t.requirement_id = ANY(%s) ORDER BY NOT t.is_primary, t.type_code""",
            (ids,)):
        by_id[t.pop("requirement_id")]["types"].append(t)
    for v in _rows(conn, """
            SELECT requirement_id, value_seq, raw_text, cell_form, num_value, operator, unit_raw,
                   cond_time_s, cond_raw, item_key, target_object, basis_standard, delegated_std,
                   equipment_key, flag
            FROM req_value WHERE requirement_id = ANY(%s) ORDER BY value_id""", (ids,)):
        by_id[v.pop("requirement_id")]["values"].append(v)
    return list(by_id.values())


REQUIREMENTS_FROM = """
        FROM requirement q
        JOIN run_document rd ON rd.document_id = q.document_id AND rd.run_id = %(run)s
        JOIN document d ON d.document_id = q.document_id
        WHERE q.req_kind = 'REQUIREMENT'
          -- 원문 위치가 없는 요구사항은 결과로 내지 않는다 (CR-02)
          AND EXISTS (SELECT 1 FROM requirement_location rl
                      WHERE rl.requirement_id = q.requirement_id)
          AND (%(doc)s::int IS NULL OR q.document_id = %(doc)s)
          AND (%(type)s::text IS NULL OR EXISTS (
                SELECT 1 FROM requirement_type_tag t
                WHERE t.requirement_id = q.requirement_id AND t.type_code = %(type)s))"""


def run_requirements(conn: psycopg.Connection, run_id: int, *, document_id: int | None = None,
                     type_code: str | None = None, limit: int = 100,
                     offset: int = 0) -> list[dict]:
    items = _rows(conn, """
        SELECT q.requirement_id, d.file_no, d.file_name, q.source_kind, q.req_kind, q.text_raw,
               q.extracted_by, q.confidence, q.is_assumed, q.rule_id, q.supplier_mark,
               q.dedup_of""" + REQUIREMENTS_FROM + """
        ORDER BY d.file_no, q.requirement_id
        LIMIT %(limit)s OFFSET %(offset)s""",
        {"run": run_id, "doc": document_id, "type": type_code, "limit": limit,
         "offset": offset})
    return _attach(conn, items, run_id)


def count_requirements(conn: psycopg.Connection, run_id: int, *, document_id: int | None = None,
                       type_code: str | None = None) -> int:
    """거름 조건을 적용한 요구사항 전체 개수 (목록 API의 X-Total-Count)."""
    return _rows(conn, "SELECT count(*) AS n" + REQUIREMENTS_FROM,
                 {"run": run_id, "doc": document_id, "type": type_code})[0]["n"]


def run_pairs(conn: psycopg.Connection, run_id: int) -> list[dict]:
    return _rows(conn, """
        SELECT p.pair_id, da.file_no AS file_no_a, db.file_no AS file_no_b, p.relation,
               p.status, p.evidence
        FROM document_pair p
        JOIN document da ON da.document_id = p.document_id_a
        JOIN document db ON db.document_id = p.document_id_b
        WHERE p.document_id_a IN (SELECT document_id FROM run_document WHERE run_id = %(r)s)
          AND p.document_id_b IN (SELECT document_id FROM run_document WHERE run_id = %(r)s)
        ORDER BY da.file_no, db.file_no""", {"r": run_id})


def run_risks(conn: psycopg.Connection, run_id: int) -> list[dict]:
    risks = _rows(conn, """
        SELECT f.risk_id, f.risk_kind, f.status, f.item_key, k.name_ko AS item_name, f.facts,
               f.explanation_ai, f.explanation_drop_reason, f.explanation_check, e.expression
        FROM risk_flag f LEFT JOIN risk_expression e USING (expr_id)
        LEFT JOIN item_key k ON k.item_key = f.item_key
        WHERE f.run_id = %s ORDER BY f.risk_id""", (run_id,))
    if not risks:
        return []
    members = _rows(conn, """
        SELECT m.risk_id, q.requirement_id, q.text_raw, v.raw_text AS value_raw
        FROM risk_flag_member m
        JOIN requirement q USING (requirement_id)
        LEFT JOIN req_value v ON v.value_id = m.value_id
        WHERE m.risk_id = ANY(%s) ORDER BY m.risk_id, q.requirement_id""",
        ([r["risk_id"] for r in risks],))
    locations: dict[int, list[dict]] = {}
    for loc in _rows(conn, LOCATIONS, (list({m["requirement_id"] for m in members}), run_id,
                                       run_id)):
        locations.setdefault(loc.pop("requirement_id"), []).append(loc)
    by_id = {r["risk_id"]: r | {"members": []} for r in risks}
    for m in members:
        m["locations"] = locations.get(m["requirement_id"], [])
        by_id[m.pop("risk_id")]["members"].append(m)
    return list(by_id.values())


def _locations(conn: psycopg.Connection, requirement_ids,
               run_id: int | None) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    for loc in _rows(conn, LOCATIONS, (list(set(requirement_ids)), run_id, run_id)):
        out.setdefault(loc.pop("requirement_id"), []).append(loc)
    return out


def _with_locations(conn: psycopg.Connection, rows: list[dict], run_id: int,
                    key: str = "requirement_id") -> list[dict]:
    """원문 위치가 없는 결과는 내지 않는다 (CR-02)."""
    locations = _locations(conn, [r[key] for r in rows if r[key] is not None], run_id)
    out = []
    for r in rows:
        r["locations"] = locations.get(r[key], [])
        if r["locations"]:
            out.append(r)
    return out


JUDGMENTS = """
    SELECT j.judgment_id, j.requirement_id, j.equipment_group, j.result, j.reason_code,
           j.reason_text, j.product_code, j.product_selected_by, j.product_value_raw,
           j.product_value_unit, j.margin_value, j.margin_kind, j.margin_direction,
           j.is_assumed, j.review_status, v.raw_text AS req_value_raw, v.num_value AS req_num,
           v.unit_raw, v.cond_time_s, v.item_key, k.name_ko AS item_name, tr.item_name_raw,
           tt.type_code, rt.type_name, j.query_sent_at,
           (SELECT user_name FROM app_user WHERE user_id = j.query_sent_by) AS query_sent_by_name
    FROM judgment j
    JOIN req_value v ON v.value_id = j.value_id
    JOIN requirement q ON q.requirement_id = j.requirement_id
    LEFT JOIN table_row tr ON tr.row_id = q.row_id
    LEFT JOIN item_key k ON k.item_key = v.item_key
    LEFT JOIN requirement_type_tag tt ON tt.requirement_id = j.requirement_id AND tt.is_primary
    LEFT JOIN requirement_type rt ON rt.type_code = tt.type_code"""

# 거르기: 판정 값, 설비 묶음, 주 유형, 검색어(항목 이름·영문 항목명·원문 문장), 확정 안 한 것만
JUDGMENTS_WHERE = """
        WHERE j.run_id = %(run)s AND j.is_current
          AND (%(result)s::text IS NULL OR j.result = %(result)s)
          AND (%(group)s::text IS NULL OR j.equipment_group = %(group)s)
          AND (%(type)s::text IS NULL OR tt.type_code = %(type)s)
          AND (%(q)s::text IS NULL OR k.name_ko ILIKE %(q)s OR tr.item_name_raw ILIKE %(q)s
               OR q.text_raw ILIKE %(q)s)
          AND (NOT %(unconfirmed)s OR j.review_status = 'CANDIDATE')
          AND (%(ids)s::int[] IS NULL OR j.judgment_id = ANY(%(ids)s))"""

# 판정 순서: 일탈 후보 → 질의 후보 → 확인 필요 → 작성 필요 → 준수
PRIORITY = """CASE j.result WHEN 'DEVIATION_CANDIDATE' THEN 1 WHEN 'QUERY_CANDIDATE' THEN 2
    WHEN 'NEEDS_REVIEW' THEN 3 WHEN 'WARRANTY_TO_FILL' THEN 4 ELSE 5 END"""


def _judgment_params(run_id: int, result: str | None, group: str | None, type_code: str | None,
                     q: str | None, unconfirmed: bool, ids: list[int] | None = None) -> dict:
    text = (q or "").strip()
    return {"run": run_id, "result": result, "group": group, "type": type_code,
            "q": f"%{text}%" if text else None, "unconfirmed": unconfirmed, "ids": ids}


def _past_ids(conn: psycopg.Connection, run_id: int, past: str | None,
              revised: bool = False) -> list[int] | None:
    """past=differs: 지난 사람 판정과 다른 줄만 (add-review-memory).
    revised: 마지막 개정에서 바뀌거나 추가된 줄만 (add-revision-notice). 둘 다면 둘 다 맞는 줄."""
    from rfp_agent.pipeline.review_memory import differing_ids

    ids = differing_ids(conn, run_id) if past == "differs" else None
    if revised:
        rev = list(revised_ids(conn, run_id))
        ids = rev if ids is None else [i for i in ids if i in set(rev)]
    return ids


def run_judgments(conn: psycopg.Connection, run_id: int, *, result: str | None = None,
                  group: str | None = None, type_code: str | None = None, q: str | None = None,
                  unconfirmed: bool = False, priority: bool = False, limit: int = 100,
                  offset: int = 0, past: str | None = None, revised: bool = False) -> list[dict]:
    from rfp_agent.pipeline.review_memory import hints

    order = f"{PRIORITY}, j.judgment_id" if priority else "j.judgment_id"
    rows = _rows(conn, JUDGMENTS + JUDGMENTS_WHERE + f"""
        ORDER BY {order} LIMIT %(limit)s OFFSET %(offset)s""",
        _judgment_params(run_id, result, group, type_code, q, unconfirmed,
                         _past_ids(conn, run_id, past, revised))
        | {"limit": limit, "offset": offset})
    found = hints(conn, run_id, [r["judgment_id"] for r in rows]) if rows else {}
    rev = revised_ids(conn, run_id) if rows else {}
    for r in rows:
        r["past_decision"] = found.get(r["judgment_id"])
        r["revised"] = rev.get(r["judgment_id"])
    return _with_locations(conn, rows, run_id)


def count_judgments(conn: psycopg.Connection, run_id: int, *, result: str | None = None,
                    group: str | None = None, type_code: str | None = None,
                    q: str | None = None, unconfirmed: bool = False,
                    past: str | None = None, revised: bool = False) -> int:
    sql = JUDGMENTS.split("FROM judgment j", 1)[1]
    return _rows(conn, "SELECT count(*) AS n FROM judgment j" + sql + JUDGMENTS_WHERE,
                 _judgment_params(run_id, result, group, type_code, q, unconfirmed,
                                  _past_ids(conn, run_id, past, revised)))[0]["n"]


def judgment_counts(conn: psycopg.Connection, run_id: int) -> dict:
    """판정 칩 건수: 판정 값마다, 확정 안 한 수, 그중 준수. 반려한 판정은 세지 않는다."""
    rows = _rows(conn, """
        SELECT result, count(*) AS n,
               count(*) FILTER (WHERE review_status = 'CANDIDATE') AS open
        FROM judgment WHERE run_id = %s AND is_current AND review_status <> 'REJECTED'
        GROUP BY result""", (run_id,))
    from rfp_agent.pipeline.review_memory import counts

    by_result = {r["result"]: r["n"] for r in rows}
    seen, differs = counts(conn, run_id)
    return {"by_result": by_result, "total": sum(by_result.values()),
            "unconfirmed": sum(r["open"] for r in rows),
            "unconfirmed_comply": sum(r["open"] for r in rows if r["result"] == "COMPLY"),
            "past_seen": seen, "past_differs": differs}


def run_equipment(conn: psycopg.Connection, run_id: int) -> list[dict]:
    """설비 묶음마다 지금 비교 제품, 고른 주체, 후보 제품, 판정 수."""
    from rfp_agent.pipeline.judge import group_contexts
    from rfp_agent.pipeline.selection import candidates

    rows = _rows(conn, """
        SELECT j.equipment_group, array_agg(DISTINCT j.product_code)
                   FILTER (WHERE j.product_code IS NOT NULL) AS products,
               max(j.product_selected_by) AS selected_by, count(*) AS judgments,
               count(*) FILTER (WHERE j.result = 'DEVIATION_CANDIDATE') AS deviations,
               count(*) FILTER (WHERE j.reason_code = 'PRODUCT_AMBIGUOUS') AS ambiguous,
               c.product_code AS chosen_product
        FROM judgment j
        LEFT JOIN run_product_choice c ON c.run_id = j.run_id
                                      AND c.equipment_group = j.equipment_group
        WHERE j.run_id = %s AND j.is_current
        GROUP BY j.equipment_group, c.product_code ORDER BY j.equipment_group""", (run_id,))
    if not rows:
        return []
    ids = [r[0] for r in conn.execute(
        """SELECT d.document_id FROM run_document rd JOIN document d USING (document_id)
           WHERE rd.run_id = %s AND d.readable""", (run_id,))]
    groups, products = group_contexts(conn, run_id, ids)
    for r in rows:
        ctx = groups.get(r["equipment_group"])
        r["label"] = ctx.label if ctx else None
        r["family"] = ctx.family if ctx else None
        r["candidates"] = [p.code for p in candidates(products, ctx)] if ctx else []
    return rows


def run_warranty(conn: psycopg.Connection, run_id: int, *, status: str | None = None,
                 limit: int = 100, offset: int = 0) -> list[dict]:
    rows = _rows(conn, """
        SELECT w.candidate_id, w.judgment_id, j.requirement_id, j.equipment_group, v.item_key,
               k.name_ko AS item_name, tr.item_name_raw, w.candidate_value, w.candidate_unit,
               w.source_kind, w.product_code, w.pm_column, w.fixed_key, w.status,
               w.reason_code, w.is_assumed
        FROM warranty_candidate w
        JOIN judgment j USING (judgment_id)
        JOIN req_value v ON v.value_id = j.value_id
        JOIN requirement q ON q.requirement_id = j.requirement_id
        LEFT JOIN table_row tr ON tr.row_id = q.row_id
        LEFT JOIN item_key k ON k.item_key = v.item_key
        WHERE w.run_id = %(run)s AND (%(status)s::text IS NULL OR w.status = %(status)s)
        ORDER BY w.candidate_id LIMIT %(limit)s OFFSET %(offset)s""",
        {"run": run_id, "status": status, "limit": limit, "offset": offset})
    return _with_locations(conn, rows, run_id)


def count_warranty(conn: psycopg.Connection, run_id: int, *, status: str | None = None) -> int:
    return _rows(conn, """
        SELECT count(*) AS n FROM warranty_candidate w
        WHERE w.run_id = %(run)s AND (%(status)s::text IS NULL OR w.status = %(status)s)""",
        {"run": run_id, "status": status})[0]["n"]


def run_losses(conn: psycopg.Connection, run_id: int) -> list[dict]:
    rows = _rows(conn, """
        SELECT loss_calc_id, clause_requirement_id AS requirement_id, product_code,
               price_noload, price_load, price_aux, price_unit, loss_noload_kw, loss_load_kw,
               loss_aux_kw, total_usd, formula, status, reason_code, is_assumed,
               price_requirement_ids
        FROM loss_calc WHERE run_id = %s ORDER BY loss_calc_id""", (run_id,))
    prices = _locations(conn, [i for r in rows for i in r["price_requirement_ids"] or []], run_id)
    for r in rows:
        # 종류별 가산액과 단가 행 위치 (손실 환산 탭 표, CR-01: 계산은 여기서)
        r["amounts"] = amounts(
            {"noload": float(r["price_noload"]), "load": float(r["price_load"]),
             "aux": float(r["price_aux"])},
            {"noload": _float(r["loss_noload_kw"]), "load": _float(r["loss_load_kw"]),
             "aux": _float(r["loss_aux_kw"])})
        if r["reason_code"] == "PRICE_UNIT":           # 단위가 $/kW가 아니면 곱하지 않는다 (CR-10)
            r["amounts"] = {k: None for k in r["amounts"]}
        r["price_locations"] = [loc for i in r["price_requirement_ids"] or []
                                for loc in prices.get(i, [])]
    return _with_locations(conn, rows, run_id)


def _float(value) -> float | None:
    return None if value is None else float(value)


def run_checks(conn: psycopg.Connection, run_id: int) -> list[dict]:
    """공학 규칙 검산 (FR-12). 근거 위치는 최대 순간 전류 행과 단시간 전류 행."""
    rows = _rows(conn, """
        SELECT c.check_id, c.rule_code, c.result, c.reason_code, c.expected_ka, c.factor,
               p.requirement_id, i.requirement_id AS ik_requirement_id,
               p.item_key AS peak_item_key, p.num_value AS peak_ka, p.raw_text AS peak_raw,
               i.item_key AS ik_item_key, i.num_value AS ik_ka, i.raw_text AS ik_raw,
               f.num_value AS frequency_hz
        FROM engineering_check c
        JOIN req_value p ON p.value_id = c.peak_value_id
        JOIN req_value i ON i.value_id = c.ik_value_id
        LEFT JOIN req_value f ON f.value_id = c.freq_value_id
        WHERE c.run_id = %s ORDER BY c.check_id""", (run_id,))
    rows = _with_locations(conn, rows, run_id)
    ik_locations = _locations(conn, [r["ik_requirement_id"] for r in rows], run_id)
    for r in rows:
        r["ik_locations"] = ik_locations.get(r["ik_requirement_id"], [])
    return rows


def run_outputs(conn: psycopg.Connection, run_id: int,
                list_kind: str | None = None) -> list[dict]:
    """일탈·질의 목록 항목. 항목마다 근거 요구사항과 원문 위치, 연결된 항목을 붙인다."""
    items = _rows(conn, """
        SELECT item_id, list_kind, list_name, text_draft, number_check, number_detail,
               drafted_by, status, is_assumed, basis_requirement_id
        FROM output_item WHERE run_id = %(run)s
          AND (%(kind)s::text IS NULL OR list_kind = %(kind)s)
        ORDER BY list_kind, item_id""", {"run": run_id, "kind": list_kind})
    if not items:
        return []
    ids = [i["item_id"] for i in items]
    sources = _rows(conn, """
        SELECT s.item_id, s.source_seq, s.judgment_id, s.risk_id, s.check_id,
               COALESCE(j.requirement_id, m.requirement_id, pv.requirement_id) AS requirement_id,
               iv.requirement_id AS ik_requirement_id
        FROM output_item_source s
        LEFT JOIN judgment j USING (judgment_id)
        LEFT JOIN risk_flag_member m ON m.risk_id = s.risk_id
        LEFT JOIN engineering_check c ON c.check_id = s.check_id
        LEFT JOIN req_value pv ON pv.value_id = c.peak_value_id
        LEFT JOIN req_value iv ON iv.value_id = c.ik_value_id
        WHERE s.item_id = ANY(%s) ORDER BY s.item_id, s.source_seq""", (ids,))
    locations = _locations(conn, [r for s in sources
                                  for r in (s["requirement_id"], s["ik_requirement_id"]) if r],
                           run_id)
    links: dict[int, list[int]] = {}
    for a, b in conn.execute("SELECT item_id, linked_item_id FROM output_item_link "
                             "WHERE item_id = ANY(%s) ORDER BY 1, 2", (ids,)):
        links.setdefault(a, []).append(b)
    by_id = {i["item_id"]: i | {"sources": [], "locations": [],
                                "linked_items": links.get(i["item_id"], [])} for i in items}
    for s in sources:
        item = by_id[s.pop("item_id")]
        ik_requirement = s.pop("ik_requirement_id")    # 검산: 단시간 전류 행도 근거 위치
        item["sources"].append(s)
        for req_id in (s["requirement_id"], ik_requirement):
            for loc in locations.get(req_id, []):
                if loc not in item["locations"]:
                    item["locations"].append(loc)
    return [i for i in by_id.values() if i["locations"]]


def run_proposals(conn: psycopg.Connection, run_id: int) -> list[dict]:
    rows = _rows(conn, """
        SELECT point_id, point_kind, requirement_id, product_code, judgment_id, loss_calc_id,
               fault_link_id, text_draft, basis, number_check, number_detail, drafted_by,
               is_assumed, status
        FROM proposal_point WHERE run_id = %s ORDER BY point_id""", (run_id,))
    return _with_locations(conn, rows, run_id)


def submission_check(conn: psycopg.Connection, run_id: int) -> dict | None:
    rows = _rows(conn, """
        SELECT deviation_candidates, deviation_listed, missing_judgment_ids, open_queries,
               ar_codes, checked_at
        FROM submission_check WHERE run_id = %s ORDER BY check_id DESC LIMIT 1""", (run_id,))
    return rows[0] if rows else None


def users(conn: psycopg.Connection) -> list[dict]:
    return _rows(conn, "SELECT user_id, user_name, role FROM app_user ORDER BY user_id", ())


def run_list(conn: psycopg.Connection, limit: int = 50) -> list[dict]:
    rows = _rows(conn, f"""
        SELECT r.run_id, r.stage, r.started_at, r.finished_at, r.graph_state->>'step' AS step,
               r.graph_state->'detail' AS step_detail,
               COALESCE((r.graph_state->>'updated_at')::timestamptz, r.started_at)
                   AS step_updated_at,
               r.failed_step, r.error_message, {REVIEW_INFO},
               (SELECT string_agg(d.file_name, ', ' ORDER BY d.file_no)
                  FROM run_document rd JOIN document d USING (document_id)
                 WHERE rd.run_id = r.run_id) AS files,
               {COUNTS},
               ap.approver_id, ap.approver, ap.requested_by_id, ap.requested_by,
               ap.requested_at, ap.decision, ap.decided_at, r.graph_state->'revision' AS revision
        FROM review_run r
        -- 가장 최근 상신 하나. 그것이 취소한 상신이면 결재 칸은 모두 비운다
        LEFT JOIN LATERAL (
            SELECT a.approver_id, u.user_name AS approver, a.requested_by AS requested_by_id,
                   q.user_name AS requested_by, a.requested_at, a.decision, a.decided_at
            FROM (SELECT * FROM approval WHERE run_id = r.run_id
                  ORDER BY approval_id DESC LIMIT 1) a
            LEFT JOIN app_user u ON u.user_id = a.approver_id
            LEFT JOIN app_user q ON q.user_id = a.requested_by
            WHERE a.decision IS DISTINCT FROM 'WITHDRAWN') ap ON TRUE
        ORDER BY r.run_id DESC LIMIT %s""", (limit,))
    return [_with_revision(r) for r in rows]


def requirement(conn: psycopg.Connection, requirement_id: int,
                run_id: int | None = None) -> dict | None:
    """요구사항 하나의 원문, 원문 위치, 유형, 값 (화면의 "원문 보기")."""
    items = _rows(conn, """
        SELECT q.requirement_id, d.file_no, d.file_name, q.source_kind, q.req_kind, q.text_raw,
               q.extracted_by, q.confidence, q.is_assumed, q.rule_id, q.supplier_mark,
               q.dedup_of
        FROM requirement q JOIN document d USING (document_id)
        WHERE q.requirement_id = %s""", (requirement_id,))
    return _attach(conn, items, run_id)[0] if items else None
