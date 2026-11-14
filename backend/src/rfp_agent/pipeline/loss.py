"""FR-13 손실 환산. 가산액 = Σ(단가 × 손실값). 코드만 계산하고 단위는 환산하지 않는다 (CR-10).

단가는 데이터시트의 $/kW 행 셋(무부하·부하·보조), 손실값은 그 표 비교 제품의 product_master 손실 칸.
"""

import re
from collections import defaultdict
from dataclasses import dataclass

import psycopg

from rfp_agent.pipeline.numbers import fmt
from rfp_agent.pipeline.products import load_products

PRICE_UNIT = re.compile(r"/\s*kW\b", re.IGNORECASE)
DOLLAR_PER_KW = re.compile(r"^(?:US\s?)?\$\s*/\s*kW$|^USD\s*/\s*kW$", re.IGNORECASE)
KINDS = [("noload", re.compile(r"no[- ]?load|무부하", re.IGNORECASE)),
         ("aux", re.compile(r"auxiliar|보조", re.IGNORECASE)),
         ("load", re.compile(r"load\s+loss|부하\s*손실|부하", re.IGNORECASE))]
UNIT_SEP = ", "                  # 단가 단위가 종류마다 다를 때 (단위 안의 "/"와 겹치지 않게)
KIND_NAMES = {"noload": "무부하", "load": "부하", "aux": "보조"}


@dataclass
class PriceRow:
    requirement_id: int
    kind: str
    price: float
    unit: str
    row_order: int
    product_code: str | None


def price_kind(name: str) -> str | None:
    return next((kind for kind, pattern in KINDS if pattern.search(name or "")), None)


def amounts(prices: dict[str, float], losses: dict[str, float | None]) -> dict[str, float | None]:
    """종류별 가산액 (단가 × 손실값). 손실값이 없는 종류는 None."""
    return {k: prices[k] * losses[k] if losses[k] is not None else None
            for k in ("noload", "load", "aux")}


def compute(prices: dict[str, float], losses: dict[str, float | None]) -> tuple[float | None, str]:
    """종류별 가산액 합계와 계산식. 손실값이 하나라도 없으면 합계는 None."""
    parts = [f"{fmt(prices[k])} × {fmt(losses[k]) if losses[k] is not None else '?'}"
             for k in ("noload", "load", "aux")]
    if any(losses[k] is None for k in ("noload", "load", "aux")):
        return None, " + ".join(parts) + " (손실값 없음)"
    parts_usd = list(amounts(prices, losses).values())
    total = sum(parts_usd)
    return total, (" + ".join(parts) + " = " + " + ".join(fmt(a) for a in parts_usd)
                   + f" = {fmt(total)} $")


def _price_rows(conn: psycopg.Connection, run_id: int) -> dict[int, list[PriceRow]]:
    tables: dict[int, list[PriceRow]] = defaultdict(list)
    for req_id, num, unit, name, table_id, row_order, product in conn.execute(
            """SELECT j.requirement_id, v.num_value, v.unit_raw, tr.item_name_raw, tr.table_id,
                      tr.row_order, j.product_code
               FROM judgment j
               JOIN req_value v ON v.value_id = j.value_id
               JOIN requirement r ON r.requirement_id = j.requirement_id
               JOIN table_row tr ON tr.row_id = r.row_id
               WHERE j.run_id = %s AND j.is_current AND v.num_value IS NOT NULL
                 AND v.unit_raw ~* '/\\s*kW'
               ORDER BY tr.table_id, tr.row_order""", (run_id,)):
        kind = price_kind(name)
        if kind and PRICE_UNIT.search(unit or ""):
            tables[table_id].append(PriceRow(req_id, kind, float(num), unit.strip(), row_order,
                                             product))
    return tables


def _clause(conn: psycopg.Connection, table_id: int, before: int) -> int | None:
    """단가 행 바로 앞의 비용 영향(COST) 조항 — 손실 환산 조항."""
    row = conn.execute(
        """SELECT r.requirement_id FROM requirement r
           JOIN table_row tr ON tr.row_id = r.row_id
           JOIN requirement_type_tag t ON t.requirement_id = r.requirement_id
           WHERE tr.table_id = %s AND tr.row_order < %s AND t.type_code = 'COST'
           ORDER BY tr.row_order DESC LIMIT 1""", (table_id, before)).fetchone()
    return row[0] if row else None


def build_losses(conn: psycopg.Connection, run_id: int) -> int:
    products = {p.code: p for p in load_products(conn)}
    rows = []
    for table_id, prices in _price_rows(conn, run_id).items():
        by_kind: dict[str, PriceRow] = {}
        for p in prices:
            by_kind.setdefault(p.kind, p)
        if set(by_kind) != {"noload", "load", "aux"}:
            continue
        first = min(by_kind.values(), key=lambda p: p.row_order)
        clause = _clause(conn, table_id, first.row_order) or first.requirement_id
        product = products.get(first.product_code) if first.product_code else None
        units = {p.unit for p in by_kind.values()}
        price = {k: p.price for k, p in by_kind.items()}
        losses = dict(zip(("noload", "load", "aux"),
                          product.losses if product else (None, None, None), strict=True))
        if not all(DOLLAR_PER_KW.match(u) for u in units):
            total, formula, status, reason = None, "단가 단위가 $/kW가 아님", "NEEDS_REVIEW", \
                "PRICE_UNIT"
        elif product is None:
            total, formula, status, reason = None, "비교 제품 없음", "NEEDS_REVIEW", "NO_PRODUCT"
        else:
            total, formula = compute(price, losses)
            status, reason = ("CALCULATED", None) if total is not None else (
                "NEEDS_REVIEW", "NO_LOSS_VALUE")
        rows.append((run_id, clause, product.code if product else None, price["noload"],
                     price["load"], price["aux"], losses["noload"], losses["load"],
                     losses["aux"], total, bool(product and product.loss_is_assumed),
                     UNIT_SEP.join(sorted(units)), status, reason, formula,
                     [by_kind[k].requirement_id for k in ("noload", "load", "aux")]))
    with conn.transaction():
        # 제안 포인트가 손실 환산을 가리키므로 먼저 지운다 (제안 단계에서 다시 만든다)
        conn.execute("DELETE FROM proposal_point WHERE run_id = %s", (run_id,))
        conn.execute("DELETE FROM loss_calc WHERE run_id = %s", (run_id,))
        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO loss_calc (run_id, clause_requirement_id, product_code,
                       price_noload, price_load, price_aux, loss_noload_kw, loss_load_kw,
                       loss_aux_kw, total_usd, is_assumed, price_unit, status, reason_code,
                       formula, price_requirement_ids)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                rows)
    return len(rows)


def recalculate(conn: psycopg.Connection, loss_calc_id: int, noload: float | None,
                load: float | None, aux: float | None) -> dict:
    """엔지니어가 손실값을 바꾸면 다시 계산한다. 직접 넣은 값은 카탈로그 값이 아니라 팀 가정이다."""
    row = conn.execute(
        "SELECT price_noload, price_load, price_aux, price_unit FROM loss_calc "
        "WHERE loss_calc_id = %s", (loss_calc_id,)).fetchone()
    if row is None:
        raise KeyError(loss_calc_id)
    prices = {"noload": float(row[0]), "load": float(row[1]), "aux": float(row[2])}
    units_ok = all(DOLLAR_PER_KW.match(u) for u in (row[3] or "").split(UNIT_SEP))
    losses = {"noload": noload, "load": load, "aux": aux}
    total, formula = compute(prices, losses) if units_ok else (None, "단가 단위가 $/kW가 아님")
    status = "CALCULATED" if total is not None else "NEEDS_REVIEW"
    reason = None if total is not None else ("PRICE_UNIT" if not units_ok else "NO_LOSS_VALUE")
    conn.execute(
        """UPDATE loss_calc SET loss_noload_kw = %s, loss_load_kw = %s, loss_aux_kw = %s,
               total_usd = %s, formula = %s, status = %s, reason_code = %s, is_assumed = TRUE
           WHERE loss_calc_id = %s""",
        (noload, load, aux, total, formula, status, reason, loss_calc_id))
    conn.commit()
    return {"total_usd": total, "formula": formula, "status": status, "is_assumed": True}
