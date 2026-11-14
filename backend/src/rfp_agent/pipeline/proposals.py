"""FR-14 기술 제안 포인트 후보. 준수 + 강점 여유, 손실 환산 합계, 현장 이력(FR-15)을 코드가 고른다.

근거 칸(요구 원문 위치, 제품 행)이 비면 만들지 않는다 (K12 = 0). 문장은 근거 값만으로 쓰고
숫자는 자리표시자로 둔 뒤 코드가 채우고 대조한다 (CR-07). 경쟁 제품 비교 문장은 쓰지 않는다.
"""

import psycopg
from psycopg.rows import dict_row

from rfp_agent.llm import tasks
from rfp_agent.llm.client import LLM
from rfp_agent.pipeline.field_history import find_matches
from rfp_agent.pipeline.numbers import Filled, fill, filled_with, fmt

ASSUMED = " (팀 가정)"


def _margin_points(conn: psycopg.Connection, run_id: int) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            """SELECT j.judgment_id, j.requirement_id, j.product_code, j.product_value_raw,
                      j.margin_value, j.margin_kind, j.is_assumed, v.item_key, v.num_value,
                      v.unit_raw, v.cond_time_s, k.name_ko
               FROM judgment j JOIN req_value v ON v.value_id = j.value_id
               LEFT JOIN item_key k ON k.item_key = v.item_key
               WHERE j.run_id = %s AND j.is_current AND j.result = 'COMPLY'
                 AND j.review_status <> 'REJECTED'
                 AND j.margin_direction = 'STRENGTH' AND j.product_code IS NOT NULL
                 AND EXISTS (SELECT 1 FROM requirement_location rl
                             WHERE rl.requirement_id = j.requirement_id)
               ORDER BY j.judgment_id""", (run_id,)).fetchall()
    points, seen = [], set()
    for r in rows:
        key = (r["item_key"], r["num_value"], r["unit_raw"], r["cond_time_s"], r["product_code"],
               r["margin_kind"], r["margin_value"])
        if key in seen:                     # 같은 요구가 여러 표에 반복되면 포인트 하나
            continue
        seen.add(key)
        name, unit = r["name_ko"] or r["item_key"], (r["unit_raw"] or "").strip()
        req = fmt(float(r["num_value"]))
        values = {"v1": req, "v2": r["product_value_raw"] or "", "p": r["product_code"],
                  "m": fmt(float(r["margin_value"]))}
        marks = {"v1": "요구값", "v2": "제품값", "p": "제품", "m": "여유"}
        if r["margin_kind"] == "TIME_RATIO":
            values["t"] = fmt(float(r["cond_time_s"]))
            marks["t"] = "요구 시간(초)"
            template = (f"{name} 요구 {{v1}} {unit}({{t}}초)에 대해 {{p}}는 {{v2}}를 견뎌 "
                        f"시간 기준 {{m}}배 여유가 있습니다.")
            basis = f"요구 {req} {unit} ({values['t']}초) · 제품 {r['product_code']} " \
                    f"{values['v2']} · 여유 시간 {values['m']}배"
        else:
            template = (f"{name} 요구 {{v1}} {unit}에 대해 {{p}}는 {{v2}}로 "
                        f"{{m}} {unit} 여유가 있습니다.")
            basis = f"요구 {req} {unit} · 제품 {r['product_code']} {values['v2']} · " \
                    f"여유 {values['m']} {unit}"
        points.append({"kind": "MARGIN", "requirement_id": r["requirement_id"],
                       "product_code": r["product_code"], "judgment_id": r["judgment_id"],
                       "loss_calc_id": None, "template": template, "values": values,
                       "marks": marks, "basis": basis, "is_assumed": r["is_assumed"],
                       "facts": template})
    return points


def _loss_points(conn: psycopg.Connection, run_id: int) -> list[dict]:
    points = []
    for (loss_id, clause, product, noload, load, aux, total,
         assumed) in conn.execute(
            """SELECT loss_calc_id, clause_requirement_id, product_code, loss_noload_kw,
                      loss_load_kw, loss_aux_kw, total_usd, is_assumed
               FROM loss_calc WHERE run_id = %s AND total_usd IS NOT NULL
                 AND product_code IS NOT NULL ORDER BY loss_calc_id""", (run_id,)):
        values = {"l1": fmt(float(noload)), "l2": fmt(float(load)), "l3": fmt(float(aux)),
                  "t": fmt(float(total)), "p": product}
        marks = {"l1": "무부하 손실(kW)", "l2": "부하 손실(kW)", "l3": "보조 손실(kW)",
                 "t": "손실 환산 가산액($)", "p": "제품"}
        template = ("{p}의 손실 환산 가산액은 무부하 {l1} kW·부하 {l2} kW·보조 {l3} kW 기준 "
                    "{t} $입니다. 손실이 적을수록 평가 가격에서 유리합니다.")
        basis = (f"제품 {product} 손실 {values['l1']} / {values['l2']} / {values['l3']} kW · "
                 f"가산액 {values['t']} $" + (ASSUMED if assumed else ""))
        points.append({"kind": "LOSS", "requirement_id": clause, "product_code": product,
                       "judgment_id": None, "loss_calc_id": loss_id, "template": template,
                       "values": values, "marks": marks, "basis": basis, "is_assumed": assumed,
                       "facts": template})
    return points


def _field_points(conn: psycopg.Connection, run_id: int) -> list[dict]:
    """현장 이력 후보. 문장은 고장 사전의 증상·원인·조치만으로 코드가 쓴다 (AI에 맡기지 않음)."""
    points = []
    for m in find_matches(conn, run_id):
        link = m.link
        values = {"f": link.fault_id, "s": link.symptom, "c": link.root_cause, "a": link.action,
                  "n": str(link.cases)}
        template = (f"{link.name_ko} 요구와 이어지는 현장 고장 {{f}} (제품군 {link.family}). "
                    "증상: {s}. 원인: {c}. 조치: {a}. 해결 사례 {n}건.")
        files = ", ".join(str(n) for n in m.file_nos)
        basis = (f"요구 항목 {link.name_ko} · 같은 요구 {m.count}곳 (파일 {files}) · "
                 f"고장 사전 {link.fault_id} ({link.family}) · 해결 사례 {link.cases}건 "
                 f"(의심 사례 {link.suspects}건 제외)")
        points.append({"kind": "FIELD", "requirement_id": m.requirement_id,
                       "product_code": None, "judgment_id": None, "loss_calc_id": None,
                       "fault_link_id": link.fault_link_id, "template": template,
                       "values": values, "basis": basis, "is_assumed": False})
    return points


def build_proposals(conn: psycopg.Connection, run_id: int, llm: LLM | None) -> int:
    points = _margin_points(conn, run_id) + _loss_points(conn, run_id)
    with conn.cursor(row_factory=dict_row) as cur:
        previous = {(r["point_kind"], r["requirement_id"], r["basis"]): r for r in cur.execute(
            "SELECT point_kind, requirement_id, basis, status, text_draft, drafted_by, "
            "number_check, number_detail FROM proposal_point WHERE run_id = %s",
            (run_id,)).fetchall()}

    def by_engineer(p: dict) -> bool:
        old = previous.get((p["kind"], p["requirement_id"], p["basis"]))
        return bool(old) and old["drafted_by"] == "ENGINEER"

    def kept(p: dict) -> dict | None:
        # 같은 근거·같은 값의 포인트는 언어 모델에 다시 묻지 않는다 (CR-11)
        old = previous.get((p["kind"], p["requirement_id"], p["basis"]))
        if old and not by_engineer(p) and filled_with(old["text_draft"], p["values"]):
            return old
        return None

    fresh = [p for p in points if kept(p) is None and not by_engineer(p)]
    if llm is not None and fresh:
        texts = tasks.draft_sentences(llm, "기술 제안 포인트",
                                      [(p["facts"], p["marks"]) for p in fresh])
        # 자리표시자를 다 쓰지 않은 포인트 등은 그 포인트만 코드 기본 문장 (update-ai-answer-checks)
        fresh_texts = {id(p): (t, "AI") if t is not None else (p["template"], "CODE")
                       for p, t in zip(fresh, texts, strict=True)}
    else:
        fresh_texts = {id(p): (p["template"], "CODE") for p in fresh}
    field = _field_points(conn, run_id)
    points += field
    fresh_texts |= {id(p): (p["template"], "CODE") for p in field}
    reviewed = {k: r for k, r in previous.items() if r["status"] != "CANDIDATE"}
    with conn.transaction():
        conn.execute("DELETE FROM proposal_point WHERE run_id = %s", (run_id,))
        for p in points:
            status = "CANDIDATE"
            key = (p["kind"], p["requirement_id"], p["basis"])
            if prev := reviewed.get(key):
                # 다시 만들어도 같은 근거의 포인트면 채택·버림·고친 문장을 이어 쓴다
                status = prev["status"]
            if by_engineer(p):
                # 엔지니어가 쓴 문장은 이어 쓰고 숫자 대조만 지금 값으로 다시 한다
                filled = fill(previous[key]["text_draft"].removesuffix(ASSUMED), p["values"])
                by = "ENGINEER"
            elif (old := kept(p)) and p["kind"] != "FIELD":
                filled = Filled(old["text_draft"].removesuffix(ASSUMED), old["number_check"],
                                old["number_detail"])
                by = old["drafted_by"]
            else:
                template, by = fresh_texts[id(p)]
                filled = fill(template, p["values"])
            text = filled.text + (ASSUMED if p["is_assumed"] else "")
            conn.execute(
                """INSERT INTO proposal_point (run_id, point_kind, requirement_id, product_code,
                       judgment_id, loss_calc_id, fault_link_id, text_draft, number_check,
                       is_assumed, status, basis, number_detail, drafted_by)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (run_id, p["kind"], p["requirement_id"], p["product_code"], p["judgment_id"],
                 p["loss_calc_id"], p.get("fault_link_id"), text, filled.check,
                 p["is_assumed"], status, p["basis"], filled.detail, by))
    return len(points)
