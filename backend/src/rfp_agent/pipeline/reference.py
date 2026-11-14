"""기준 데이터 읽기 (SCR-16 제품표, SCR-17 판정 규칙). 고치기는 pipeline/rule_edit.py.

끈(삭제한) 사전 줄은 목록에서 뺀다.

빈 칸은 빈 값 그대로 낸다 (CR-04). 쓰인 횟수는 현재 판정(is_current)과 위험 조건 후보만 센다.
"""

import psycopg
from psycopg.rows import dict_row

# 판정·보증값·손실 환산이 읽는 제품표 칸 (item_pm_mapping의 칸 + 손실 3종). 설명 글 칸은 뺀다.
# 제품군마다 "판정에 쓰는 칸"은 그 제품군 제품 중 하나라도 값이 있는 칸이다 (빈 칸 수의 기준).
VALUE_COLUMNS = ("rated_voltage_kv", "rated_current_a", "short_circuit_ka", "rated_frequency",
                 "rated_capacity", "standards", "ip_rating", "operating_temp", "weight_kg",
                 "lightning_impulse_kv", "power_freq_withstand_kv", "switching_impulse_kv",
                 "peak_current_ka", "making_current_ka", "breaking_time_ms", "closing_time_ms",
                 "gas_leakage_percent", "partial_discharge_pc", "cooling_type", "insulation_medium",
                 "maintenance_months", "service_life_years", "warranty_months",
                 "noload_loss_kw", "load_loss_kw", "aux_loss_kw")
LIST_COLUMNS = ("product_code", "product_name", "family", "rated_voltage_kv", "rated_current_a",
                "short_circuit_ka", "rated_frequency", "rated_capacity", "rated_capacity_unit",
                "weight_kg", "lightning_impulse_kv", "power_freq_withstand_kv",
                "switching_impulse_kv", "peak_current_ka", "making_current_ka",
                "breaking_time_ms", "closing_time_ms", "gas_leakage_percent",
                "partial_discharge_pc", "cooling_type", "insulation_medium",
                "maintenance_months", "service_life_years", "warranty_months",
                "noload_loss_kw", "load_loss_kw", "aux_loss_kw", "loss_is_assumed",
                "comparison_values_assumed", "comparison_values_source",
                "is_assumed", "is_design_card", "source_doc", "lifecycle_status")

USED_IN_LIMIT = 100          # 상세의 "판정에 쓰임" 줄은 최근 실행부터 100줄까지 (수는 used로 따로)
USED = """(SELECT count(*) FROM judgment j
           WHERE j.product_code = p.product_code AND j.is_current)"""


class NotFound(LookupError):
    pass


def _family_columns(cur) -> dict[str, list[str]]:
    """제품군 → 판정에 쓰는 칸 (그 제품군에서 값이 하나라도 있는 칸)."""
    counts = ", ".join(f"count({c}) AS {c}" for c in VALUE_COLUMNS)
    rows = cur.execute(f"SELECT family, {counts} FROM product_master GROUP BY family").fetchall()
    return {r["family"]: [c for c in VALUE_COLUMNS if r[c]] for r in rows}


def _decorate(row: dict, columns: dict[str, list[str]]) -> dict:
    used = columns.get(row["family"], [])
    row["value_columns"] = used
    row["empty_columns"] = [c for c in used if row.get(c) is None]
    row["empty_count"] = len(row["empty_columns"])
    row["is_assumed"] = row["is_assumed"] == "Y"
    if "comparison_values_assumed" in row:
        row["comparison_values_assumed"] = row["comparison_values_assumed"] == "Y"
    return row


def _where(family: str | None, q: str | None, cards: bool = True) -> tuple[str, dict]:
    where = ["(%(family)s::text IS NULL OR p.family = %(family)s)",
             "(%(cards)s OR NOT p.is_design_card)",
             "(%(q)s::text IS NULL OR p.product_code ILIKE %(like)s"
             " OR p.product_name ILIKE %(like)s)"]
    return " AND ".join(where), {"family": family, "q": q, "like": f"%{q}%" if q else None,
                                 "cards": cards}


def products(conn: psycopg.Connection, family: str | None = None, q: str | None = None,
             offset: int = 0, limit: int = 100, cards: bool = True) -> list[dict]:
    """제품 목록. 제품군 → 코드 순서 (CR-11). cards=False면 설계 사례 카드를 뺀다."""
    where, params = _where(family, q or None, cards)
    cols = ", ".join(f"p.{c}" for c in LIST_COLUMNS)
    with conn.cursor(row_factory=dict_row) as cur:
        columns = _family_columns(cur)
        rows = cur.execute(
            f"""SELECT {cols}, {USED} AS used FROM product_master p WHERE {where}
                ORDER BY p.family, p.product_code OFFSET %(offset)s LIMIT %(limit)s""",
            {**params, "offset": offset, "limit": limit}).fetchall()
    return [_decorate(r, columns) for r in rows]


def count_products(conn: psycopg.Connection, family: str | None = None,
                   q: str | None = None, cards: bool = True) -> int:
    where, params = _where(family, q or None, cards)
    sql = f"SELECT count(*) FROM product_master p WHERE {where}"
    return conn.execute(sql, params).fetchone()[0]


def families(conn: psycopg.Connection) -> list[dict]:
    """제품군 탭: 제품 수, 빈 칸이 있는 제품 수와 빈 칸 수, 팀 가정 제품 수, 설계 사례 카드 수."""
    with conn.cursor(row_factory=dict_row) as cur:
        columns = _family_columns(cur)
        rows = cur.execute(
            f"SELECT {', '.join('p.' + c for c in LIST_COLUMNS)} FROM product_master p "
            "ORDER BY p.family, p.product_code").fetchall()
    out: dict[str, dict] = {}
    for r in rows:
        r = _decorate(r, columns)
        f = out.setdefault(r["family"], {"family": r["family"], "products": 0, "with_empty": 0,
                                         "assumed": 0, "design_cards": 0, "empty_cells": 0})
        f["products"] += 1
        f["empty_cells"] += r["empty_count"]
        f["with_empty"] += 1 if r["empty_count"] else 0
        f["assumed"] += 1 if r["is_assumed"] or r["loss_is_assumed"] \
            or r["comparison_values_assumed"] else 0
        f["design_cards"] += 1 if r["is_design_card"] else 0
    return list(out.values())


def product(conn: psycopg.Connection, code: str) -> dict:
    """제품 하나의 전체 칸과 쓰인 곳: 현재 판정, 제안 포인트, 같은 제품군 현장 이력."""
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute(f"SELECT p.*, {USED} AS used FROM product_master p "
                          "WHERE p.product_code = %s", (code,)).fetchone()
        if row is None:
            raise NotFound(f"제품 {code}이(가) 제품표에 없습니다.")
        row = _decorate(row, _family_columns(cur))
        row["used_runs"] = cur.execute(
            "SELECT count(DISTINCT run_id) AS n FROM judgment "
            "WHERE product_code = %s AND is_current",
            (code,)).fetchone()["n"]
        row["used_in"] = cur.execute(
            """SELECT j.run_id, 'RV-' || extract(year FROM r.started_at)::int || '-'
                      || lpad(r.run_id::text, 3, '0') AS review_no,
                      r.project_name, r.review_name, j.judgment_id, j.equipment_group,
                      COALESCE(k.name_ko, tr.item_name_raw, v.item_key) AS item_name, j.result,
                      j.product_selected_by, v.item_key, r.due_date
               FROM judgment j JOIN review_run r ON r.run_id = j.run_id
               JOIN req_value v ON v.value_id = j.value_id
               LEFT JOIN item_key k ON k.item_key = v.item_key
               LEFT JOIN requirement q ON q.requirement_id = j.requirement_id
               LEFT JOIN table_row tr ON tr.row_id = q.row_id
               WHERE j.product_code = %s AND j.is_current
               ORDER BY j.run_id DESC, j.judgment_id LIMIT %s""", (code, USED_IN_LIMIT)).fetchall()
        row["proposals"] = cur.execute(
            """SELECT point_id, run_id, point_kind, status, text_draft, is_assumed
               FROM proposal_point WHERE product_code = %s ORDER BY run_id DESC, point_id""",
            (code,)).fetchall()
        row["field_history"] = cur.execute(
            """SELECT l.fault_link_id, l.item_key, k.name_ko AS item_name, l.fault_id,
                      f.symptom, f.root_cause, f.action, l.confirmed_by,
                      (SELECT count(*) FROM resolution_case c
                       WHERE c.fault_id = l.fault_id AND c.suspect_reason IS NULL) AS cases
               FROM fault_link l JOIN fault_catalog f ON f.fault_id = l.fault_id
               JOIN item_key k ON k.item_key = l.item_key
               WHERE l.product_family = %s ORDER BY l.fault_link_id""",
            (row["family"],)).fetchall()
    return row


def compare_rules(conn: psycopg.Connection) -> list[dict]:
    """비교 방향 사전과 쓴 판정 수 (현재 판정만). 강점 방향이 비면 판정처럼 항목 기본값을 쓴다."""
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            """SELECT c.compare_rule_id, c.table_name, c.item_no, c.item_key, k.name_ko,
                      c.direction, c.time_condition,
                      COALESCE(c.strength_direction, k.strength_direction) AS strength_direction,
                      c.strength_direction AS own_strength_direction,
                      c.process_note,
                      (SELECT count(*) FROM judgment j
                       WHERE j.compare_rule_id = c.compare_rule_id AND j.is_current) AS used
               FROM compare_rule c LEFT JOIN item_key k ON k.item_key = c.item_key
               WHERE c.active ORDER BY c.compare_rule_id""").fetchall()


def items(conn: psycopg.Connection) -> list[dict]:
    """표준 항목과 같은 뜻 원문 표현, 연결된 제품표 칸, 그 항목을 쓴 현재 판정 수."""
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            """SELECT k.item_key, k.name_ko, k.default_direction, k.strength_direction, k.note,
                      m.pm_column, m.fixed_key,
                      COALESCE(array_agg(a.alias_text ORDER BY a.alias_text)
                               FILTER (WHERE a.alias_id IS NOT NULL), '{}') AS aliases,
                      (SELECT count(*) FROM judgment j JOIN req_value v ON v.value_id = j.value_id
                       WHERE v.item_key = k.item_key AND j.is_current) AS used
               FROM item_key k LEFT JOIN item_alias a ON a.item_key = k.item_key
               LEFT JOIN item_pm_mapping m ON m.item_key = k.item_key
               WHERE k.active GROUP BY k.item_key, m.pm_column, m.fixed_key
               ORDER BY k.item_key""").fetchall()
    return rows


def risk_expressions(conn: psycopg.Connection) -> list[dict]:
    """위험 표현 사전과 그 표현으로 찾은 위험 조건 후보 수."""
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            """SELECT e.expr_id, e.expression, e.language, e.risk_kind, e.context_rule,
                      (SELECT count(*) FROM risk_flag f WHERE f.expr_id = e.expr_id) AS used
               FROM risk_expression e WHERE e.active ORDER BY e.risk_kind, e.expr_id""").fetchall()


def doc_kind_rules(conn: psycopg.Connection) -> list[dict]:
    """문서 종류 규칙 사전과 그 종류로 규칙이 분류한 문서 수 (같은 종류는 한 줄뿐)."""
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            """SELECT r.doc_kind_rule_id, r.priority, r.doc_kind, r.name_pattern, r.page_pattern,
                      r.note,
                      (SELECT count(*) FROM document d WHERE d.doc_kind = r.doc_kind
                         AND d.classify_by = 'RULE') AS used
               FROM doc_kind_rule r ORDER BY r.priority""").fetchall()
