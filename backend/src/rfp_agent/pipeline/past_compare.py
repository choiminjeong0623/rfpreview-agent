"""지난 RFP 비교 (SCR-08-7, change add-past-compare).

같은 고객사의 지난 검토와 이번 검토의 판정 줄을 짝지어 달라진 요구만 보인다.
짝짓기·구분·판정 비교는 모두 코드로 한다(CR-01). 단위 환산은 하지 않는다(CR-10).

- 같은 설비: 제품군 + 설비 최고 전압(없으면 설비 묶음 이름)
- 같은 항목: 표준 항목(item_key) + 표의 항목 이름(공백·대소문자·번호 무시)
- 한 열쇠에 값이 여러 개면 값 묶음을 비교하고, 판정은 가장 무거운 것을 보인다
- 반려한 판정(사람이 해당 없음으로 뺀 줄)은 양쪽 모두 뺀다
"""

import re
from dataclasses import dataclass, field

import psycopg
from psycopg.rows import dict_row

from rfp_agent.pipeline.queries import REVIEW_INFO

DONE_STAGES = ("ENGINEER_REVIEW", "APPROVAL", "APPROVED", "REJECTED")
# 무거운 판정부터 (판정 칸에 하나만 보일 때 고르는 순서)
SEVERITY = ["DEVIATION_CANDIDATE", "QUERY_CANDIDATE", "NEEDS_REVIEW", "WARRANTY_TO_FILL",
            "COMPLY"]
KIND_ORDER = {"chg": 0, "new": 1, "del": 2}
RESULT_NAMES = {"DEVIATION_CANDIDATE": "일탈 후보", "QUERY_CANDIDATE": "질의 후보",
                "NEEDS_REVIEW": "확인 필요", "WARRANTY_TO_FILL": "작성 필요", "COMPLY": "준수"}
TARGET_LIMIT = 20


class NotFound(Exception):
    pass


def _norm_customer(name: str | None) -> str:
    return re.sub(r"\s+", " ", (name or "").strip()).lower()


def _norm_item(name: str | None) -> str:
    text = (name or "").lower()
    text = re.sub(r"^[\s\d.()\-a-z]{0,6}[.)]\s+", "", text)      # 앞 번호 "1.", "a)" 등
    return re.sub(r"[^0-9a-z가-힣]+", " ", text).strip()


def _target_rows(conn: psycopg.Connection, where: str, params: tuple) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(f"""
            SELECT r.run_id, r.stage, r.started_at, {REVIEW_INFO},
                   (SELECT string_agg(d.file_name, ', ' ORDER BY d.file_no)
                      FROM run_document rd JOIN document d USING (document_id)
                     WHERE rd.run_id = r.run_id) AS files,
                   (SELECT array_agg(DISTINCT j.product_code ORDER BY j.product_code)
                      FROM judgment j WHERE j.run_id = r.run_id AND j.is_current
                       AND j.product_code IS NOT NULL) AS products,
                   (SELECT count(*) FROM judgment j WHERE j.run_id = r.run_id
                       AND j.is_current) AS judgments
            FROM review_run r WHERE {where}
            ORDER BY r.started_at DESC, r.run_id DESC""", params).fetchall()


def _clean(row: dict) -> dict:
    keep = ("run_id", "review_no", "stage", "started_at", "project_name", "review_name",
            "customer_name", "files", "judgments")
    return {**{k: row[k] for k in keep}, "products": row["products"] or []}


def targets(conn: psycopg.Connection, run_id: int) -> dict:
    """비교할 수 있는 지난 검토: 고객사 글자가 같고 처리를 마친 다른 검토, 최근 것부터."""
    me = conn.execute("SELECT customer_name FROM review_run WHERE run_id = %s",
                      (run_id,)).fetchone()
    if me is None:
        raise NotFound(f"검토 실행 {run_id}이(가) 없습니다.")
    customer = _norm_customer(me[0])
    if not customer:
        return {"customer_name": None, "targets": []}
    rows = _target_rows(
        conn,
        "r.run_id <> %s AND r.stage = ANY(%s) AND lower(regexp_replace(btrim("
        "COALESCE(r.customer_name, '')), '\\s+', ' ', 'g')) = %s",
        (run_id, list(DONE_STAGES), customer))
    return {"customer_name": me[0].strip(), "targets": [_clean(r) for r in rows[:TARGET_LIMIT]]}


@dataclass
class Line:
    equipment: str
    item_name: str
    item_raw: str | None = None                   # 표의 항목 이름 (영문 원문)
    values: set[str] = field(default_factory=set)
    nums: set[tuple[float, str]] = field(default_factory=set)
    results: set[str] = field(default_factory=set)
    requirement_ids: set[int] = field(default_factory=set)

    @property
    def result(self) -> str | None:
        return next((r for r in SEVERITY if r in self.results), None)

    @property
    def shown(self) -> str:
        return " / ".join(sorted(self.values)) or "값 없음"


def _value_text(raw: str | None, unit: str | None) -> str:
    raw = (raw or "").strip()
    if unit and raw and unit not in raw:
        return f"{raw} {unit}"
    return raw


def _lines(conn: psycopg.Connection, run_id: int) -> dict[tuple, Line]:
    from rfp_agent.pipeline.judge import group_contexts

    ids = [r[0] for r in conn.execute(
        """SELECT d.document_id FROM run_document rd JOIN document d USING (document_id)
           WHERE rd.run_id = %s AND d.readable ORDER BY 1""", (run_id,))]
    groups, _ = group_contexts(conn, run_id, ids) if ids else ({}, [])
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute("""
            SELECT j.requirement_id, j.equipment_group, j.result, v.item_key, v.raw_text,
                   v.num_value, v.unit_raw, k.name_ko, tr.item_name_raw, q.text_raw
            FROM judgment j
            JOIN req_value v ON v.value_id = j.value_id
            LEFT JOIN item_key k ON k.item_key = v.item_key
            LEFT JOIN requirement q ON q.requirement_id = j.requirement_id
            LEFT JOIN table_row tr ON tr.row_id = q.row_id
            WHERE j.run_id = %s AND j.is_current AND j.review_status <> 'REJECTED'
            ORDER BY j.judgment_id""", (run_id,)).fetchall()
    out: dict[tuple, Line] = {}
    for r in rows:
        ctx = groups.get(r["equipment_group"])
        family = ctx.family if ctx else None
        um = ctx.um if ctx else None
        label = ctx.label if ctx else (r["equipment_group"] or "")
        equip_key = (family or "", f"{um:g}" if um is not None else label)
        equipment = " ".join(p for p in (f"{um:g} kV" if um is not None else label,
                                         family or "") if p)
        # 표 항목 이름이 없으면(표 밖 문장) 표준 항목 이름, 그것도 없으면 원문 앞부분으로 짝짓는다
        name_key = (_norm_item(r["item_name_raw"]) or _norm_item(r["name_ko"])
                    or _norm_item((r["text_raw"] or "")[:80]))
        key = (equip_key, r["item_key"] or "", name_key)
        line = out.get(key)
        if line is None:
            line = out[key] = Line(equipment, r["name_ko"] or r["item_name_raw"]
                                    or (r["text_raw"] or "")[:60] or "항목 없음",
                                    r["item_name_raw"] if r["name_ko"] else None)
        text = _value_text(r["raw_text"], r["unit_raw"])
        if text:
            line.values.add(text)
        if r["num_value"] is not None:
            line.nums.add((float(r["num_value"]), (r["unit_raw"] or "").strip()))
        line.results.add(r["result"])
        line.requirement_ids.add(r["requirement_id"])
    return out


def _direction(before: Line, after: Line) -> str | None:
    """값이 하나씩이고 단위가 같을 때만 올라감·내려감 (단위 환산 없음, CR-10)."""
    if len(before.nums) != 1 or len(after.nums) != 1:
        return None
    (a, ua), (b, ub) = next(iter(before.nums)), next(iter(after.nums))
    if ua != ub or a == b:
        return None
    return "요구 값이 올라감" if b > a else "요구 값이 내려감"


def compare(conn: psycopg.Connection, run_id: int, other_id: int) -> dict:
    """이번 검토(run_id)와 지난 검토(other_id)의 달라진 요구. 같은 입력이면 같은 결과(CR-11)."""
    found = _target_rows(conn, "r.run_id = %s", (other_id,))
    if not found or conn.execute("SELECT 1 FROM review_run WHERE run_id = %s",
                                 (run_id,)).fetchone() is None:
        raise NotFound("비교할 검토가 없습니다.")
    if run_id == other_id:
        raise ValueError("같은 검토끼리는 비교하지 않습니다.")
    if found[0]["stage"] not in DONE_STAGES:
        raise ValueError("처리를 마친 검토만 비교할 수 있습니다.")
    now, past = _lines(conn, run_id), _lines(conn, other_id)
    rows, same = [], 0
    for key in sorted(set(now) | set(past)):
        a, b = past.get(key), now.get(key)
        if a and b:
            if a.values == b.values and a.result == b.result:
                same += 1
                continue
            notes = []
            if a.values == b.values:
                notes.append("요구 값 같음")
            elif d := _direction(a, b):
                notes.append(d)
            notes.append("판정 같음" if a.result == b.result else "판정 바뀜")
            rows.append(_row("chg", b, a.shown, b.shown, a.result, b.result, " · ".join(notes)))
        elif b:
            rows.append(_row("new", b, "—", b.shown, None, b.result, "지난번에 없던 요구"))
        else:
            was = RESULT_NAMES.get(a.result or "", "")
            note = "이번에는 요구 없음" + (f" · 지난번 {was}" if was else "")
            rows.append(_row("del", a, a.shown, "—", a.result, None, note))
    rows.sort(key=lambda r: (KIND_ORDER[r["kind"]],
                             SEVERITY.index(r["after_result"] or r["before_result"] or "COMPLY"),
                             r["equipment"], r["item_name"], r["after"], r["before"]))
    return {"target": _clean(found[0]), "rows": rows, "same": same}


def _row(kind: str, line: Line, before: str, after: str, before_result: str | None,
         after_result: str | None, note: str) -> dict:
    return {"kind": kind, "equipment": line.equipment, "item_name": line.item_name,
            "item_raw": line.item_raw,
            "before": before, "after": after, "before_result": before_result,
            "after_result": after_result, "note": note,
            "requirement_id": min(line.requirement_ids) if kind != "del" else None}
