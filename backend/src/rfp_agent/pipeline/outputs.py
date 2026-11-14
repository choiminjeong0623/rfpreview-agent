"""FR-09 일탈·질의 목록 초안과 제출 전 누락 점검.

대상 고르기, 같은 요구 묶기, 질의↔일탈 연결, 숫자 채우기·대조, 누락 점검은 코드가 한다.
AI는 문장 초안만 쓰고 숫자는 자리표시자로 둔다 (CR-07). 모두 "후보"(DRAFT)다 (CR-08).
"""

import re
from collections import defaultdict
from dataclasses import dataclass, field

import psycopg
from psycopg.rows import dict_row

from rfp_agent.llm import tasks
from rfp_agent.llm.client import LLM
from rfp_agent.pipeline import queries
from rfp_agent.pipeline.compare import unit_key
from rfp_agent.pipeline.numbers import Filled, fill, filled_with, fmt

# 발주처 양식 이름 ("Clarification, Exception & Deviation List", "Schedule of Deviations")
DEVIATION_FORM = re.compile(
    r"(?:clarification,?\s*)?(?:exceptions?\s*(?:&|and)\s*)?deviations?\s+(?:list|schedule|form)"
    r"|(?:schedule|list|statement)\s+of\s+(?:technical\s+)?(?:deviations?|exceptions?)"
    r"|일탈\s*(?:목록|표)", re.IGNORECASE)
QUERY_FORM = re.compile(r"(?:schedule|list)\s+of\s+(?:clarifications?|queries|questions)"
                        r"|질의\s*(?:목록|서)", re.IGNORECASE)
# 서면 문의 조항 (질의 목록의 근거 조항)
QUERY_CLAUSE = re.compile(r"seek clarification|request(?:s)? for clarification|"
                          r"written (?:query|queries|request)|서면\s*(?:질의|문의)", re.IGNORECASE)
DEFAULT_NAMES = {"DEVIATION": "일탈 목록", "QUERY": "질의 목록"}
RISK_NAMES = {"BLANKET": "포괄 조항", "COST_SHIFT": "비용 전가", "OPEN_SCOPE": "범위 모호"}


@dataclass
class Draft:
    list_kind: str
    key: tuple
    facts: str                                      # AI에게 주는 사실 (숫자는 자리표시자)
    template: str                                   # AI가 없을 때 코드 문장
    marks: dict[str, str]                           # 자리표시자 → 뜻
    values: dict[str, str]                          # 자리표시자 → 근거 값
    judgment_ids: list[int] = field(default_factory=list)
    risk_ids: list[int] = field(default_factory=list)
    check_ids: list[int] = field(default_factory=list)
    requirement_ids: set[int] = field(default_factory=set)
    is_assumed: bool = False


def find_form(conn: psycopg.Connection, document_ids: list[int],
              pattern: re.Pattern) -> tuple[str | None, int | None]:
    """문서에서 양식 이름(또는 조항)을 찾아 원문 그대로와 그 요구사항 id를 돌려준다."""
    for req_id, text in conn.execute(
            """SELECT q.requirement_id, q.text_raw FROM requirement q
               JOIN document d USING (document_id)
               WHERE q.document_id = ANY(%s) ORDER BY d.file_no, q.requirement_id""",
            (document_ids,)):
        if m := pattern.search(text):
            return m.group(0).strip(), req_id
    for title in conn.execute(
            "SELECT title FROM section WHERE document_id = ANY(%s) ORDER BY section_id",
            (document_ids,)):
        if title[0] and (m := pattern.search(title[0])):
            return m.group(0).strip(), None
    return None, None


OPERATORS = {"<": "<", "<=": "≤", ">": ">", ">=": "≥"}


def _judgment_drafts(conn: psycopg.Connection, run_id: int) -> list[Draft]:
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            """SELECT j.judgment_id, j.requirement_id, j.result, j.reason_code, j.product_code,
                      j.product_value_raw, j.is_assumed, v.item_key, v.num_value, v.operator,
                      v.unit_raw, v.raw_text, k.name_ko
               FROM judgment j JOIN req_value v ON v.value_id = j.value_id
               LEFT JOIN item_key k ON k.item_key = v.item_key
               WHERE j.run_id = %s AND j.is_current AND j.review_status <> 'REJECTED'
                 AND j.result IN ('DEVIATION_CANDIDATE', 'QUERY_CANDIDATE')
               ORDER BY j.judgment_id""", (run_id,)).fetchall()
    drafts: dict[tuple, Draft] = {}
    for r in rows:
        kind = "DEVIATION" if r["result"] == "DEVIATION_CANDIDATE" else "QUERY"
        num = float(r["num_value"]) if r["num_value"] is not None else None
        # 비교 기호를 붙여야 "<0.5"와 0.5가 같은 숫자로 읽히지 않는다 (요구 미만·초과 조건)
        req = (OPERATORS.get(r["operator"] or "", "") + fmt(num)
               if num is not None and r["reason_code"] != "MULTI_VALUE"
               else (r["raw_text"] or "").strip())
        unit = (r["unit_raw"] or "").strip()
        key = (kind, "J", r["item_key"], req, unit_key(unit), r["product_code"], r["reason_code"])
        draft = drafts.get(key)
        if draft is None:
            name = r["name_ko"] or r["item_key"] or "항목"
            values = {"v1": req}
            if r["product_code"]:
                values["p"] = r["product_code"]
            if kind == "DEVIATION":
                values["v2"] = r["product_value_raw"] or ""
                marks = {"v1": "요구값", "v2": "제품값", "p": "비교 제품"}
                facts = (f"항목: {name}, 요구값 {{v1}} {unit}, 비교 제품 {{p}}의 값 {{v2}}, "
                         "판정: 일탈 후보")
                template = (f"{name} 요구값 {{v1}} {unit}에 대해 비교 제품 {{p}}의 값은 {{v2}}로 "
                            "요구를 그대로 맞추지 못합니다. 일탈로 제출할지 확인이 필요합니다.")
            elif r["reason_code"] != "MULTI_VALUE":     # 엔지니어가 질의로 바꾼 판정
                marks = {"v1": "요구값", "p": "비교 제품"}
                facts = f"항목: {name}, 요구값 {{v1}} {unit}, 적용 방법을 질의"
                template = f"{name} 요구값 {{v1}} {unit}의 적용 범위와 조건을 질의합니다."
            else:
                marks = {"v1": "요구 칸의 값들", "p": "비교 제품"}
                facts = f"항목: {name}, 요구 칸 {{v1}} {unit}에 값이 여럿, 어느 값인지 질의"
                template = (f"{name} 요구 칸에 값이 여럿({{v1}} {unit}) 있어 어느 값을 적용하는지 "
                            "질의합니다.")
            # 비교 제품이 없으면 AI에 "비교 제품" 자리표시자를 주지 않는다
            if "p" not in values:
                marks = {k: v for k, v in marks.items() if k != "p"}
            draft = drafts[key] = Draft(kind, key, facts, " ".join(template.split()), marks,
                                        values)
        draft.judgment_ids.append(r["judgment_id"])
        draft.requirement_ids.add(r["requirement_id"])
        draft.is_assumed |= r["is_assumed"]
    return list(drafts.values())


def _risk_drafts(conn: psycopg.Connection, run_id: int) -> list[Draft]:
    names = dict(conn.execute("SELECT item_key, name_ko FROM item_key"))
    drafts: dict[tuple, Draft] = {}
    for risk in queries.run_risks(conn, run_id):
        if risk["status"] == "CLOSED_OK":           # 엔지니어가 문제 없음으로 닫은 위험 조건
            continue
        members = risk["members"]
        if risk["risk_kind"] == "VALUE_MISMATCH":
            raws = sorted({(m["value_raw"] or "").strip() for m in members})
            key = ("QUERY", "R", risk["item_key"], tuple(raws))
            name = names.get(risk["item_key"], risk["item_key"] or "값")
            marks = {f"v{i}": f"문서 값 {i}" for i in range(1, len(raws) + 1)}
            values = {f"v{i}": raw for i, raw in enumerate(raws, start=1)}
            listed = " / ".join(f"{{v{i}}}" for i in range(1, len(raws) + 1))
            facts = f"항목: {name}, 문서마다 다른 값 {listed}, 어느 값을 따르는지 질의"
            template = f"{name} 값이 문서마다 다릅니다({listed}). 어느 값을 따르는지 질의합니다."
        else:
            key = ("QUERY", "R", risk["risk_id"])
            label = RISK_NAMES.get(risk["risk_kind"], "위험 조건")
            marks, values = {"e": "위험 표현"}, {"e": risk["expression"] or ""}
            facts = f"{label} 표현 {{e}}이(가) 있는 조항, 적용 범위를 질의"
            template = f"{label}(표현 \"{{e}}\")이 있어 적용 범위와 책임 한계를 질의합니다."
        draft = drafts.get(key)
        if draft is None:
            draft = drafts[key] = Draft("QUERY", key, facts, template, marks, values)
        draft.risk_ids.append(risk["risk_id"])
        draft.requirement_ids.update(m["requirement_id"] for m in members)
    return list(drafts.values())


def _check_drafts(conn: psycopg.Connection, run_id: int) -> list[Draft]:
    """공학 규칙 검산 위반 (FR-12) → 질의 후보. 같은 숫자의 위반은 한 건으로 묶는다."""
    names = dict(conn.execute("SELECT item_key, name_ko FROM item_key"))
    drafts: dict[tuple, Draft] = {}
    for c in queries.run_checks(conn, run_id):
        if c["result"] != "VIOLATION":
            continue
        peak, ik = float(c["peak_ka"]), float(c["ik_ka"])
        key = ("QUERY", "C", c["peak_item_key"], peak, ik, float(c["factor"]))
        draft = drafts.get(key)
        if draft is None:
            name = names.get(c["peak_item_key"], "최대 순간 전류")
            values = {"v1": fmt(ik), "v2": fmt(peak), "f": fmt(float(c["frequency_hz"])),
                      "k": fmt(float(c["factor"])), "e": fmt(float(c["expected_ka"]))}
            marks = {"v1": "단시간 전류(kA)", "v2": "요구값(kA)", "f": "주파수(Hz)",
                     "k": "배수", "e": "계산한 값(kA)"}
            facts = (f"항목: {name}, 요구값 {{v2}} kA, 같은 부위 단시간 전류 {{v1}} kA, "
                     "주파수 {f} Hz, 계산한 값 {e} kA (× {k}), 어느 값이 맞는지 질의")
            template = (f"{name} 요구값 {{v2}} kA가 같은 부위의 단시간 전류 {{v1}} kA와 주파수 "
                        "{f} Hz로 계산한 값 {e} kA(× {k})와 맞지 않습니다. 어느 값이 맞는지 "
                        "질의합니다.")
            draft = drafts[key] = Draft("QUERY", key, facts, template, marks, values)
        draft.check_ids.append(c["check_id"])
        draft.requirement_ids.update({c["requirement_id"], c["ik_requirement_id"]})
    return list(drafts.values())


def _texts(llm: LLM | None, drafts: list[Draft]) -> list[tuple[str, str]]:
    """(자리표시자 문장, 작성 주체)."""
    if llm is None or not drafts:
        return [(d.template, "CODE") for d in drafts]
    texts = tasks.draft_sentences(llm, "일탈·질의 목록", [(d.facts, d.marks) for d in drafts])
    # 자리표시자를 다 쓰지 않은 줄 등은 그 줄만 코드 기본 문장 (update-ai-answer-checks)
    return [(t, "AI") if t is not None else (d.template, "CODE")
            for t, d in zip(texts, drafts, strict=True)]


def build_outputs(conn: psycopg.Connection, run_id: int, document_ids: list[int],
                  llm: LLM | None) -> int:
    drafts = (_judgment_drafts(conn, run_id) + _risk_drafts(conn, run_id)
              + _check_drafts(conn, run_id))
    drafts.sort(key=lambda d: (d.list_kind, min(d.requirement_ids)))
    previous = _previous_items(conn, run_id)

    def kept(d: Draft) -> dict | None:
        # 같은 항목이고 근거 값도 그대로인 문장은 언어 모델에 다시 묻지 않는다. 판정 하나를
        # 고칠 때마다 모든 문장을 새로 쓰면 수십 초가 걸리고 같은 입력에 다른 문장이 나온다
        # (CR-11). 엔지니어가 쓴 문장은 값이 바뀌어도 이어 쓰고 숫자 대조만 다시 한다.
        old = previous.get((d.list_kind, repr(d.key)))
        if old and (old["drafted_by"] == "ENGINEER" or filled_with(old["text_draft"], d.values)):
            return old
        return None

    fresh = [d for d in drafts if kept(d) is None]
    fresh_texts = dict(zip((id(d) for d in fresh), _texts(llm, fresh), strict=True))
    names = {kind: find_form(conn, document_ids, pattern)
             for kind, pattern in (("DEVIATION", DEVIATION_FORM), ("QUERY", QUERY_FORM))}
    _, clause = find_form(conn, document_ids, QUERY_CLAUSE)
    reviewed = _reviewed_items(conn, run_id)
    with conn.transaction():
        clear_outputs(conn, run_id)
        by_requirement: dict[int, list[tuple[str, int]]] = defaultdict(list)
        for draft in drafts:
            status = "DRAFT"
            if prev := reviewed.get((draft.list_kind, repr(draft.key))):
                # 같은 항목을 다시 만들면 엔지니어 확인 결과(확정·빼기·고친 문장)를 이어 쓴다
                status = prev["status"]
            if (old := kept(draft)) and old["drafted_by"] == "ENGINEER":
                filled, drafted_by = fill(old["text_draft"], draft.values), "ENGINEER"
            elif old:
                filled = Filled(old["text_draft"], old["number_check"], old["number_detail"])
                drafted_by = old["drafted_by"]
            else:
                template, drafted_by = fresh_texts[id(draft)]
                filled = fill(template, draft.values)
            name, form_req = names[draft.list_kind]
            basis = form_req if draft.list_kind == "DEVIATION" else (clause or form_req)
            item_id = conn.execute(
                """INSERT INTO output_item (run_id, list_kind, text_draft, basis_requirement_id,
                       number_check, status, list_name, group_key, number_detail, drafted_by,
                       is_assumed)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   RETURNING item_id""",
                (run_id, draft.list_kind, filled.text, basis, filled.check, status,
                 name or DEFAULT_NAMES[draft.list_kind], repr(draft.key), filled.detail,
                 drafted_by, draft.is_assumed)).fetchone()[0]
            sources = ([(j, None, None) for j in draft.judgment_ids]
                       + [(None, r, None) for r in draft.risk_ids]
                       + [(None, None, c) for c in draft.check_ids])
            for seq, (judgment_id, risk_id, check_id) in enumerate(sources, start=1):
                conn.execute("INSERT INTO output_item_source (item_id, source_seq, judgment_id, "
                             "risk_id, check_id) VALUES (%s, %s, %s, %s, %s)",
                             (item_id, seq, judgment_id, risk_id, check_id))
            for req_id in draft.requirement_ids:
                by_requirement[req_id].append((draft.list_kind, item_id))
        links = set()
        for items in by_requirement.values():
            for kind_a, a in items:
                for kind_b, b in items:
                    if kind_a == "DEVIATION" and kind_b == "QUERY":
                        links.update({(a, b), (b, a)})       # 같은 요구에 일탈과 질의 (사례 15)
        for a, b in sorted(links):
            conn.execute("INSERT INTO output_item_link VALUES (%s, %s)", (a, b))
    check_submission(conn, run_id)
    return len(drafts)


def _previous_items(conn: psycopg.Connection, run_id: int) -> dict[tuple, dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            "SELECT list_kind, group_key, text_draft, number_check, number_detail, drafted_by "
            "FROM output_item WHERE run_id = %s", (run_id,)).fetchall()
    return {(r["list_kind"], r["group_key"]): r for r in rows}


def _reviewed_items(conn: psycopg.Connection, run_id: int) -> dict[tuple, dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            "SELECT list_kind, group_key, status, text_draft, drafted_by FROM output_item "
            "WHERE run_id = %s AND (status <> 'DRAFT' OR drafted_by = 'ENGINEER')",
            (run_id,)).fetchall()
    return {(r["list_kind"], r["group_key"]): r for r in rows}


def clear_outputs(conn: psycopg.Connection, run_id: int) -> None:
    items = "SELECT item_id FROM output_item WHERE run_id = %s"
    conn.execute(f"DELETE FROM output_item_link WHERE item_id IN ({items}) "
                 f"OR linked_item_id IN ({items})", (run_id, run_id))
    conn.execute(f"DELETE FROM output_item_source WHERE item_id IN ({items})", (run_id,))
    conn.execute("DELETE FROM output_item WHERE run_id = %s", (run_id,))
    conn.execute("DELETE FROM submission_check WHERE run_id = %s", (run_id,))


def check_submission(conn: psycopg.Connection, run_id: int) -> dict:
    """제출 전 누락 점검. 일탈 후보인데 일탈 목록(빼지 않은 항목)에 없는 판정을 찾는다 (AR-07)."""
    candidates = [r[0] for r in conn.execute(
        "SELECT judgment_id FROM judgment WHERE run_id = %s AND is_current "
        "AND result = 'DEVIATION_CANDIDATE' AND review_status <> 'REJECTED' "
        "ORDER BY judgment_id", (run_id,))]
    listed = {r[0] for r in conn.execute(
        """SELECT s.judgment_id FROM output_item_source s JOIN output_item i USING (item_id)
           WHERE i.run_id = %s AND i.list_kind = 'DEVIATION' AND i.status <> 'REMOVED'
             AND s.judgment_id IS NOT NULL""", (run_id,))}
    missing = [j for j in candidates if j not in listed]
    open_queries = conn.execute(
        "SELECT count(*) FROM output_item WHERE run_id = %s AND list_kind = 'QUERY' "
        "AND status = 'DRAFT'", (run_id,)).fetchone()[0]
    ar_codes = ["AR-07"] if missing else []
    conn.execute(
        """INSERT INTO submission_check (run_id, deviation_candidates, deviation_listed,
               missing_judgment_ids, open_queries, ar_codes)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (run_id, len(candidates), len(candidates) - len(missing), missing, open_queries,
         ar_codes))
    conn.commit()
    return {"deviation_candidates": len(candidates),
            "deviation_listed": len(candidates) - len(missing),
            "missing_judgment_ids": missing, "open_queries": open_queries, "ar_codes": ar_codes}
