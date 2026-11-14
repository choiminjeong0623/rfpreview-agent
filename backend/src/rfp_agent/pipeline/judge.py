"""FR-07 적합성 판정을 DB 결과로 만든다. 묶음 A·B 문서만 (CR-09).

같은 행이 여러 문서에 있으면 대표 요구사항 하나만 판정한다(위치는 대표에 모두 있다).
"다른 제품으로 바꿔 보기"는 묶음 하나만 다시 판정하고 이전 판정은 is_current = FALSE로 남긴다.
"""

import re
from collections import defaultdict
from dataclasses import dataclass

import psycopg
from psycopg.rows import dict_row

from rfp_agent.pipeline.compare import ReqValue, Verdict, compare, precheck
from rfp_agent.pipeline.extract import ROMAN
from rfp_agent.pipeline.products import Product, load_products, product_value
from rfp_agent.pipeline.selection import (
    GroupContext,
    Selection,
    family_of,
    select,
    table_voltage,
    voltage_in,
)

LIST_HEADING = re.compile(r"^\s*(?:\(?\d+\)|\(?[a-z]\))\s")      # "1) Continuous current"
# 변압기 2차·3차 권선 값은 제품표 정격 전압(1차)과 비교하지 않는다.
OTHER_WINDING = re.compile(r"secondary|tertiary|\b[LT]\.\s?V\.|neutral|2차|3차|중성점",
                           re.IGNORECASE)
# "Rated Power (230/115/22kV) / 360/360/75"처럼 이름의 전압 수와 값 수가 같으면 권선별 값이다.
PER_WINDING = re.compile(r"\d+(?:\.\d+)?(?:/\d+(?:\.\d+)?)+\s*kV", re.IGNORECASE)
COMPARE_USAGES = ("COMPARE", "BOTH")

VALUES_SQL = """
    SELECT v.value_id, v.requirement_id, v.raw_text, v.cell_form, v.num_value, v.operator,
           v.unit_raw, v.cond_time_s, v.item_key, v.basis_standard, v.flag, v.target_object,
           v.value_seq, r.source_kind, r.section_id, d.document_id, d.file_no, d.file_name,
           d.standard_system, tr.row_id, tr.table_id, t.table_name, tr.item_no,
           tr.item_name_raw, tr.unit_raw AS row_unit, p.item_name_raw AS parent_name,
           (SELECT count(*) FROM req_value w WHERE w.requirement_id = v.requirement_id)
               AS value_count,
           tr.row_id IS NOT NULL AND EXISTS (
               SELECT 1 FROM req_value w WHERE w.requirement_id = v.requirement_id
               AND w.value_seq > 1 AND w.num_value IS NOT NULL) AS multi,
           EXISTS (SELECT 1 FROM table_row c WHERE c.parent_row_id = tr.row_id) AS has_children
    FROM req_value v
    JOIN requirement r USING (requirement_id)
    JOIN document d ON d.document_id = r.document_id
    LEFT JOIN table_row tr ON tr.row_id = r.row_id
    LEFT JOIN doc_table t ON t.table_id = tr.table_id
    LEFT JOIN table_row p ON p.row_id = tr.parent_row_id
    WHERE r.document_id = ANY(%(docs)s) AND d.bundle IN ('A', 'B') AND d.judge_target
      AND r.req_kind = 'REQUIREMENT'
      AND (r.source_kind = 'TABLE_CELL' OR (r.source_kind = 'SENTENCE' AND v.item_key IS NOT NULL))
      AND (%(all)s OR r.dedup_of IS NULL OR NOT EXISTS (
            SELECT 1 FROM requirement x
            WHERE x.requirement_id = r.dedup_of AND x.document_id = ANY(%(docs)s)))
      AND EXISTS (SELECT 1 FROM requirement_location rl
                  WHERE rl.requirement_id = r.requirement_id)
    ORDER BY v.value_id"""


@dataclass
class Rule:
    rule_id: int
    direction: str
    time_condition: bool
    strength: str | None


@dataclass
class Reference:
    """판정에 쓰는 사전: 항목 기본 방향·강점 방향, 비교 방향 사전, 제품 열 연결표."""
    defaults: dict[str, tuple[str, str]]
    rules: dict[tuple[str, str, str | None], Rule]
    columns: dict[str, tuple[str | None, str]]

    @classmethod
    def load(cls, conn: psycopg.Connection) -> "Reference":
        defaults = {k: (d, s) for k, d, s in conn.execute(
            "SELECT item_key, default_direction, strength_direction FROM item_key WHERE active")}
        rules = {}
        for rid, table, no, key, direction, time, strength in conn.execute(
                "SELECT compare_rule_id, table_name, item_no, item_key, direction, "
                "time_condition, strength_direction FROM compare_rule WHERE active "
                "ORDER BY compare_rule_id"):
            rules[(table, _item_no(no), key)] = Rule(rid, direction, time, strength)
        columns = {k: (c, u) for k, c, u in conn.execute(
            "SELECT item_key, pm_column, usage FROM item_pm_mapping")}
        return cls(defaults, rules, columns)

    def rule_for(self, table: str | None, item_no: str | None, key: str | None) -> Rule | None:
        """표 이름 + 항목 번호 + 항목키가 모두 맞는 줄만 쓴다 (구분마다 번호가 다시 시작한다)."""
        if table is None:
            return None
        return self.rules.get((table, _item_no(item_no), key))

    def direction(self, rule: Rule | None, key: str | None) -> tuple[str | None, str]:
        default, strength = self.defaults.get(key, (None, "NONE")) if key else (None, "NONE")
        if rule is not None:
            return rule.direction, rule.strength or strength
        return default, strength


def _item_no(no: str | None) -> str:
    return (no or "").strip().rstrip(")").strip()


# ---------------------------------------------------------------- 설비 묶음

def _parts(conn: psycopg.Connection, table_ids: list[int]) -> dict[int, tuple[str, str]]:
    """행 id → 속한 로마 숫자 구분 (번호, 제목). 구분 행 = 로마 숫자 번호 + 요구값·단위 없음."""
    out: dict[int, tuple[str, str]] = {}
    current: dict[int, tuple[str, str]] = {}
    for row_id, table_id, no, name, required, unit in conn.execute(
            """SELECT row_id, table_id, item_no, item_name_raw, required_raw, unit_raw
               FROM table_row WHERE table_id = ANY(%s) ORDER BY table_id, row_order""",
            (table_ids,)):
        if no and ROMAN.match(no.strip()) and not (required or "").strip() \
                and not (unit or "").strip():
            current[table_id] = (no.strip().rstrip("."), (name or "").strip())
        out[row_id] = current.get(table_id, ("", ""))
    return out


def _section_titles(conn: psycopg.Connection, section_ids: set[int]) -> dict[int, list[str]]:
    rows = {sid: (parent, title) for sid, parent, title in conn.execute(
        "SELECT section_id, parent_id, title FROM section WHERE document_id IN "
        "(SELECT document_id FROM section WHERE section_id = ANY(%s))", (list(section_ids),))}
    out = {}
    for sid in section_ids:
        titles, cur = [], sid
        while cur is not None and cur in rows:
            parent, title = rows[cur]
            titles.append(title or "")
            cur = parent
        out[sid] = titles
    return out


def _fill_context(ctx: GroupContext, values: list[dict]) -> None:
    for v in values:
        key, num, unit = v["item_key"], v["num_value"], (v["unit_raw"] or "").strip()
        if num is None or v["flag"] == "RANGE":
            continue
        num = float(num)
        if key == "rated_voltage_um" and unit.lower() == "kv":
            ctx.um = max(ctx.um or 0, num)
        elif key == "nominal_voltage" and unit.lower() == "kv":
            ctx.nominals.add(num)
        elif key == "rated_frequency" and unit.lower() == "hz":
            ctx.frequencies.add(f"{num:g}")
        elif key in ("short_time_current", "breaking_current") and unit.lower() == "ka":
            ctx.isc_ka = max(ctx.isc_ka or 0, num)
        elif key == "rated_capacity" and v["value_seq_first"] and ctx.capacity is None:
            ctx.capacity = (num, unit)


def _table_contexts(by_table: dict[int, list[dict]]) -> dict[int, GroupContext]:
    """표마다 요구 정격. 쪽 넘김으로 이어지지 못한 같은 이름 표는 앞 표의 정격을 이어 받는다
    (파일 1 TS-AUTO-TR은 Word 표 여러 개로 나뉘고, 360 MVA 다음 240 MVA 데이터시트가 온다)."""
    out: dict[int, GroupContext] = {}
    previous: dict[tuple[int, str | None], GroupContext] = {}
    for table_id in sorted(by_table):
        rows = by_table[table_id]
        ctx = GroupContext(str(table_id), "", None)
        _fill_context(ctx, rows)
        key = (rows[0]["document_id"], rows[0]["table_name"])
        if (prev := previous.get(key)) is not None and rows[0]["table_name"]:
            if ctx.capacity is None and ctx.um is None:
                ctx.um, ctx.capacity = prev.um, prev.capacity
            ctx.um = ctx.um if ctx.um is not None else prev.um
            ctx.nominals = ctx.nominals or set(prev.nominals)
            ctx.frequencies = ctx.frequencies or set(prev.frequencies)
            ctx.isc_ka = ctx.isc_ka if ctx.isc_ka is not None else prev.isc_ka
        previous[key] = ctx
        out[table_id] = ctx
    return out


def build_groups(conn: psycopg.Connection, values: list[dict]) -> dict[str, GroupContext]:
    """값마다 설비 묶음 키를 붙이고(v['group']) 묶음별 요구 정격을 모은다."""
    parts = _parts(conn, list({v["table_id"] for v in values if v["table_id"]}))
    titles = _section_titles(conn, {v["section_id"] for v in values
                                    if v["section_id"] and not v["table_id"]})
    by_part: dict[str, list[dict]] = defaultdict(list)
    by_table: dict[int, list[dict]] = defaultdict(list)
    for v in values:
        v["value_seq_first"] = not v["multi"] or v["value_seq"] == 1
        if v["table_id"]:
            part_no, part_title = parts.get(v["row_id"], ("", ""))
            v["part"] = (part_no, part_title)
            by_part[f"T{v['table_id']}|{part_no}"].append(v)
            by_table[v["table_id"]].append(v)
    tables = _table_contexts(by_table)
    groups: dict[str, GroupContext] = {}
    for key, members in by_part.items():
        first = members[0]
        part_no, part_title = first["part"]
        ctx = GroupContext(key, f"파일 {first['file_no']} {first['table_name'] or '표'}"
                           f"{' ' + part_no + '. ' + part_title if part_no else ''}", None,
                           standard_system=first["standard_system"])
        _fill_context(ctx, members)
        whole = tables[first["table_id"]]
        ctx.um = ctx.um or whole.um
        ctx.nominals = ctx.nominals or whole.nominals
        if (tv := table_voltage(first["table_name"])) is not None:
            ctx.nominals.add(tv)
        ctx.frequencies = ctx.frequencies or whole.frequencies
        ctx.isc_ka = ctx.isc_ka or whole.isc_ka
        ctx.capacity = ctx.capacity or whole.capacity
        ctx.family = family_of(first["table_name"], part_title, None, first["file_name"],
                               ctx.um or (max(ctx.nominals) if ctx.nominals else None))
        groups[key] = ctx
        for v in members:
            v["group"] = key
    sentence_groups: dict[str, list[dict]] = defaultdict(list)
    for v in values:
        if v["table_id"]:
            continue
        kv = next((x for t in titles.get(v["section_id"], []) if (x := voltage_in(t))), None)
        kv = kv or voltage_in(v["file_name"])
        family = family_of(None, None, v["target_object"], v["file_name"], kv)
        key = f"S{v['document_id']}|{family}|{kv:g}" if kv else f"S{v['document_id']}|{family}|"
        v["group"] = key
        sentence_groups[key].append(v)
        if key not in groups:
            kv_text = f"{kv:g} kV" if kv else ""
            label = f"파일 {v['file_no']} 문장 {v['target_object'] or ''} {kv_text}"
            groups[key] = GroupContext(key, " ".join(label.split()), family,
                                       nominals={kv} if kv else set(),
                                       standard_system=v["standard_system"])
    for key, members in sentence_groups.items():
        _fill_context(groups[key], members)
    return groups


# ---------------------------------------------------------------- 판정

@dataclass
class Judged:
    value: dict
    verdict: Verdict
    selection: Selection
    rule: Rule | None
    product_raw: str | None = None
    product_unit: str | None = None
    product_column: str | None = None


def _is_heading(v: dict) -> bool:
    """하위 항목이 있는 빈 머리 행("Insulation level", "1) Continuous current")은
    판정하지 않는다."""
    if v["cell_form"] != "EMPTY" or v["flag"] == "REDACTED" or not v["table_id"]:
        return False
    if v["has_children"]:
        return True
    return not (v["item_no"] or "").strip() and not (v["row_unit"] or "").strip() \
        and bool(LIST_HEADING.match(v["item_name_raw"] or ""))


def judge_value(v: dict, ref: Reference, products: list[Product], ctx: GroupContext,
                override: str | None) -> Judged:
    rule = ref.rule_for(v["table_name"], v["item_no"], v["item_key"])
    direction, strength = ref.direction(rule, v["item_key"])
    req = ReqValue(raw=v["raw_text"], cell_form=v["cell_form"],
                   num=float(v["num_value"]) if v["num_value"] is not None else None,
                   operator=v["operator"], unit=v["unit_raw"],
                   time_s=float(v["cond_time_s"]) if v["cond_time_s"] is not None else None,
                   item_key=v["item_key"], basis_standard=v["basis_standard"], flag=v["flag"],
                   multi=v["multi"])
    row_label = " ".join(filter(None, [v["item_name_raw"], v["parent_name"]]))
    winding = PER_WINDING.search(v["item_name_raw"] or "")
    if req.multi and winding and len(winding.group(0).split("/")) == v["value_count"]:
        req.multi = False                       # 권선별 값: 1차(첫 값)만 제품과 비교한다
    selection = select(products, ctx, override, row_label)
    verdict = precheck(req, direction or "")
    if verdict is not None:
        return Judged(v, verdict, selection, rule)
    if selection.product is None:
        reason = "PRODUCT_AMBIGUOUS" if selection.candidates else "NO_PRODUCT"
        return Judged(v, Verdict("NEEDS_REVIEW", reason), selection, rule)
    column, usage = ref.columns.get(v["item_key"], (None, None))
    prod = product_value(selection.product, v["item_key"], column) \
        if usage in COMPARE_USAGES else None
    if selection.product.family == "TRANSFORMER" and v["item_key"] in (
            "rated_voltage_um", "rated_capacity") and (
            OTHER_WINDING.search(row_label) or v["value_seq"] > 1):
        prod = None                             # 제품표 정격은 1차 권선 값이다
    verdict = compare(req, prod, direction or "", strength,
                      time_condition=bool(rule and rule.time_condition))
    return Judged(v, verdict, selection, rule, prod.raw if prod else None,
                  prod.unit if prod else None, prod.column if prod else None)


def load_values(conn: psycopg.Connection, document_ids: list[int]) -> list[dict]:
    """판정할 값 (대표 요구사항만). 각 값에 'represents' 표시를 붙여 모든 값을 돌려준다.

    다른 문서와 같은 행(대표가 아닌 행)도 묶음의 요구 정격을 모으는 데는 쓴다.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        reps = {r["value_id"] for r in cur.execute(
            VALUES_SQL, {"docs": document_ids, "all": False}).fetchall()}
        rows = cur.execute(VALUES_SQL, {"docs": document_ids, "all": True}).fetchall()
    for r in rows:
        r["represents"] = r["value_id"] in reps and not _is_heading(r)
    return rows


def product_choices(conn: psycopg.Connection, run_id: int) -> dict[str, str]:
    return dict(conn.execute(
        "SELECT equipment_group, product_code FROM run_product_choice WHERE run_id = %s",
        (run_id,)))


def judge_run(conn: psycopg.Connection, run_id: int, document_ids: list[int],
              only_groups: set[str] | None = None) -> int:
    """판정을 만들어 저장한다. only_groups가 있으면 그 묶음만 다시 판정한다."""
    values = load_values(conn, document_ids)
    groups = build_groups(conn, values)
    ref, products = Reference.load(conn), load_products(conn)
    choices = product_choices(conn, run_id)
    targets = [v for v in values if v["represents"]
               and (only_groups is None or v["group"] in only_groups)]
    rows = []
    for v in targets:
        j = judge_value(v, ref, products, groups[v["group"]], choices.get(v["group"]))
        p = j.selection.product
        rows.append((
            run_id, v["requirement_id"], v["value_id"], p.code if p else None,
            (j.product_raw or "")[:100] or None, j.product_unit, j.verdict.result,
            j.verdict.reason, j.verdict.reason_text, j.rule.rule_id if j.rule else None,
            j.verdict.margin, j.verdict.margin_kind, j.verdict.margin_direction, v["group"],
            j.selection.chosen_by, bool(p and j.product_raw and p.value_assumed(j.product_column)),
        ))
    with conn.transaction():
        if only_groups is None:
            conn.execute("UPDATE judgment SET is_current = FALSE WHERE run_id = %s", (run_id,))
        else:
            conn.execute("UPDATE judgment SET is_current = FALSE WHERE run_id = %s "
                         "AND equipment_group = ANY(%s)", (run_id, list(only_groups)))
        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO judgment (run_id, requirement_id, value_id, product_code,
                       product_value_raw, product_value_unit, result, reason_code, reason_text,
                       compare_rule_id, margin_value, margin_kind, margin_direction,
                       equipment_group, product_selected_by, is_assumed)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                rows)
    return len(rows)


def group_contexts(conn: psycopg.Connection, run_id: int,
                   document_ids: list[int]) -> tuple[dict[str, GroupContext], list[Product]]:
    values = load_values(conn, document_ids)
    return build_groups(conn, values), load_products(conn)
