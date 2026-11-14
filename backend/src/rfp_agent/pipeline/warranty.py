"""FR-08 보증값 후보. 판정이 "보증값 작성"인 행 가운데 연결표에 있는 항목만
제품표 값이나 회사 고정값을 낸다.

값이 없으면 비워 두고 "확인 필요"(EMPTY_REVIEW). 지어내지 않는다 (CR-04).
"""

import re

import psycopg

from rfp_agent.pipeline.compare import unit_key
from rfp_agent.pipeline.numbers import fmt
from rfp_agent.pipeline.products import load_products, product_value

FILL_USAGES = ("FILL", "BOTH")
NOT_A_VALUE = re.compile(r"^\s*(comply|complied|complies|yes|ok|noted|agreed)\s*\.?$",
                         re.IGNORECASE)


def build_warranty(conn: psycopg.Connection, run_id: int) -> int:
    products = {p.code: p for p in load_products(conn)}
    mapping = {k: (col, fixed, usage) for k, col, fixed, usage in conn.execute(
        "SELECT item_key, pm_column, fixed_key, usage FROM item_pm_mapping")}
    fixed_values = dict(conn.execute("SELECT fixed_key, fixed_value FROM company_fixed_value"))
    columns = ("candidate_value, candidate_unit, source_kind, product_code, pm_column, fixed_key, "
               "status, reason_code, is_assumed")
    # 엔지니어가 확정·수정·반려한 칸은 다시 만들 때도 그대로 둔다
    reviewed = {r[0]: r[1:] for r in conn.execute(
        f"SELECT judgment_id, {columns} FROM warranty_candidate WHERE run_id = %s "
        "AND status IN ('CONFIRMED', 'REJECTED')", (run_id,))}
    rows = []
    for judgment_id, item_key, unit, product_code in conn.execute(
            """SELECT j.judgment_id, v.item_key, v.unit_raw, j.product_code
               FROM judgment j JOIN req_value v ON v.value_id = j.value_id
               WHERE j.run_id = %s AND j.is_current AND j.result = 'WARRANTY_TO_FILL'
                 AND j.review_status <> 'REJECTED'
               ORDER BY j.judgment_id""", (run_id,)):
        if judgment_id in reviewed:
            rows.append((run_id, judgment_id, *reviewed[judgment_id]))
            continue
        rows.append(_candidate(run_id, judgment_id, item_key, unit, products.get(product_code),
                               mapping, fixed_values))
    with conn.transaction():
        conn.execute("DELETE FROM warranty_candidate WHERE run_id = %s", (run_id,))
        with conn.cursor() as cur:
            cur.executemany(
                f"""INSERT INTO warranty_candidate (run_id, judgment_id, {columns})
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""", rows)
    return len(rows)


def _empty(run_id, judgment_id, reason, product=None, column=None):
    return (run_id, judgment_id, None, None, None, product.code if product else None, column,
            None, "EMPTY_REVIEW", reason, False)


def _candidate(run_id, judgment_id, item_key, unit, product, mapping, fixed_values):
    column, fixed_key, usage = mapping.get(item_key, (None, None, None))
    if usage not in FILL_USAGES:
        return _empty(run_id, judgment_id, "NOT_MAPPED")
    if fixed_key is not None:
        value = fixed_values.get(fixed_key)
        if not value:
            return _empty(run_id, judgment_id, "NO_FIXED_VALUE")
        return (run_id, judgment_id, value, None, "FIXED", None, None, fixed_key, "CANDIDATE",
                None, False)
    if product is None:
        return _empty(run_id, judgment_id, "PRODUCT_AMBIGUOUS")
    value = product_value(product, item_key, column)
    if value is None or not value.raw or NOT_A_VALUE.match(value.raw):
        return _empty(run_id, judgment_id, "NO_PRODUCT_VALUE", product, column)
    if value.num is not None:
        if unit and value.unit and unit_key(unit) != unit_key(value.unit):
            return _empty(run_id, judgment_id, "UNIT_DIFF", product, column)
        text, value_unit = fmt(value.num), value.unit
    else:
        text, value_unit = value.raw, None
    return (run_id, judgment_id, text[:200], value_unit, "PM", product.code, column, None,
            "CANDIDATE", None, product.value_assumed(column))
