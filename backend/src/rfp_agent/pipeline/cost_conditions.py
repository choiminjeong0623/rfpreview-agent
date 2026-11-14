"""FR-16 비용 조건 요약 (add-cost-conditions). 코드만 쓴다 (CR-01).

비용 영향(COST) 유형이 붙은 요구사항(주 유형이든 보조 유형이든)을 조항 종류별로 모은다.
금액은 계산하지 않고 값은 원문 문자열 그대로 둔다 (CR-10).
원문 위치가 없는 줄은 내지 않는다 (CR-02).
묶음 제한은 없다: 판정·보증값이 아니라 CR-09 대상이 아니고, 견적은 C·D 묶음 문서도 본다.
기술 판단에서 생긴 상업 영향(손실 환산 가산액, 일탈 후보)은 이미 있는 결과를 읽기만 한다.
"""

import re
from collections import defaultdict

import psycopg
from psycopg.rows import dict_row

from rfp_agent.pipeline import queries
from rfp_agent.pipeline.assignments import condition_key

# 조항 종류: 먼저 걸린 것 하나 (design 2). 화면 묶음 이름이고 판정에 쓰지 않는다.
KINDS: list[tuple[str, re.Pattern]] = [(name, re.compile(p, re.IGNORECASE)) for name, p in (
    ("지체상금", r"liquidated damages|delay damages|지체\s?상금"),
    ("책임 한도", r"limitation of liability|(total|aggregate|unlimited) liability"
              r"|liability .{0,40}\blimited\b|책임\s?한도"),
    ("하자 보증", r"\bdefects?\b|warranty period|guarantee period|하자"),
    ("이행 보증서", r"performance (security|bond|guarantee)|advance payment (guarantee|security)"
                  r"|이행\s?보증"),
    ("지급 조건", r"\bpayments?\b|지급"),
    ("가격 유효 기간", r"bid validity|remain valid for|\bvalidity\b"),
    ("인도 조건", r"\b(incoterms|cif|cip|fob|dap|ddp|exw)\b|delivery terms"),
    ("통화·환율", r"exchange rate|\bcurrenc(y|ies)\b|환율"),
    ("손실 평가", r"capitali[sz]ed|\$/kW|evaluated price"),
    ("예비품", r"\bspares?\b|spare parts|예비품"),
    ("특수 공구", r"special tools|특수\s?공구"),
    ("운반·포장", r"\b(packing|packaging|transport(ation)?|freight)\b|운반|포장"),
    ("시험 입회", r"\bwitness(ed|ing)?\b|입회"),
    ("설치 감독", r"\bsupervision\b|설치\s?감독"),
    ("교육", r"\btraining\b|교육"),
    ("무상 공급", r"free of charge|at no (additional|extra) cost|무상"),
)]
OTHER = "기타 비용"
KIND_ORDER = [k for k, _ in KINDS] + [OTHER]

BURDEN = re.compile(r"at no (additional|extra) cost|free of charge"
                    r"|at the (Contractor|Supplier|Bidder)'?s (own )?(cost|expense)"
                    r"|무상|계약\s?상대자\s?부담", re.IGNORECASE)
BURDEN_LABEL = "계약상대자 부담"
RISKS: list[tuple[str, re.Pattern]] = [
    ("책임 한도 없음",
     re.compile(r"shall not be limited|unlimited liability|책임\s?한도\s?없", re.I)),
    ("가격 조정 없음", re.compile(r"no (price )?adjustment|not be subject to (any )?(price )?"
                              r"adjustment|firm and fixed|fixed and firm", re.I)),
]

COST_SQL = """
    SELECT r.requirement_id, r.text_raw, r.source_kind, tr.item_name_raw, tr.required_raw,
           d.file_no, d.file_name, pt.type_code AS primary_type, prt.type_name AS primary_type_name,
           (SELECT array_agg(v.raw_text ORDER BY v.value_id) FROM req_value v
             WHERE v.requirement_id = r.requirement_id AND v.raw_text IS NOT NULL) AS values,
           (SELECT min(l.line_start) FROM requirement_location rl
             JOIN source_location l ON l.location_id = rl.location_id
             WHERE rl.requirement_id = r.requirement_id) AS line_start
    FROM requirement r
    JOIN run_document rd ON rd.document_id = r.document_id AND rd.run_id = %(run)s
    JOIN document d ON d.document_id = r.document_id
    JOIN requirement_type_tag ct ON ct.requirement_id = r.requirement_id AND ct.type_code = 'COST'
    LEFT JOIN requirement_type_tag pt ON pt.requirement_id = r.requirement_id AND pt.is_primary
    LEFT JOIN requirement_type prt ON prt.type_code = pt.type_code
    LEFT JOIN table_row tr ON tr.row_id = r.row_id
    WHERE r.req_kind = 'REQUIREMENT'
      AND EXISTS (SELECT 1 FROM requirement_location rl
                  WHERE rl.requirement_id = r.requirement_id)
      AND (r.dedup_of IS NULL OR NOT EXISTS (
            SELECT 1 FROM requirement x JOIN run_document xd ON xd.document_id = x.document_id
            WHERE x.requirement_id = r.dedup_of AND xd.run_id = %(run)s))
    ORDER BY d.file_no, line_start, r.requirement_id"""


def kind_of(text: str) -> str:
    return next((name for name, pattern in KINDS if pattern.search(text)), OTHER)


def risk_of(text: str) -> str | None:
    return next((name for name, pattern in RISKS if pattern.search(text)), None)


def _requests(conn: psycopg.Connection, run_id: int) -> dict[int, dict]:
    """요구사항 → 견적 담당 협조 요청 (FR-11, update-role-handoff-mail)."""
    out: dict[int, dict] = {}
    with conn.cursor(row_factory=dict_row) as cur:
        for a in cur.execute(
                "SELECT assignment_id, requirement_ids, status, mail_error FROM assignment "
                "WHERE run_id = %s AND assignee_role = 'COST' AND point_id IS NULL",
                (run_id,)):
            for req in a["requirement_ids"]:
                out[req] = a
    return out


def cost_conditions(conn: psycopg.Connection, run_id: int) -> list[dict]:
    """비용 조건 요약. 같은 조건이 반복되면 한 줄로 묶고 원문 위치를 모두 둔다."""
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(COST_SQL, {"run": run_id}).fetchall()
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        groups[condition_key(r)].append(r)
    locations = queries._locations(conn, [r["requirement_id"] for r in rows], run_id)
    requests = _requests(conn, run_id)
    out = []
    for members in groups.values():
        first = members[0]
        text = first["text_raw"]
        request = next((requests[m["requirement_id"]] for m in members
                        if m["requirement_id"] in requests), None)
        values = list(dict.fromkeys(v for m in members for v in (m["values"] or [])))
        out.append({
            "requirement_id": first["requirement_id"],
            "requirement_ids": [m["requirement_id"] for m in members],
            "kind": kind_of(text),
            "text": text,
            "values": values,                               # 원문 문자열 그대로 (CR-10)
            "burden": BURDEN_LABEL if BURDEN.search(text) else None,
            "risk": risk_of(text),
            "primary_type": first["primary_type"],
            "primary_type_name": first["primary_type_name"],
            "repeat_count": len(members),
            "role": "COST",
            "assignment_id": request["assignment_id"] if request else None,
            "request_status": request["status"] if request else None,
            "mail_error": request["mail_error"] if request else None,
            "file_name": first["file_name"],
            "locations": [loc for m in members for loc in locations.get(m["requirement_id"], [])],
        })
    out.sort(key=lambda c: KIND_ORDER.index(c["kind"]))     # 종류 순서, 같은 종류는 원문 순서
    return out


def commercial_impacts(conn: psycopg.Connection, run_id: int) -> list[dict]:
    """기술 판단에서 생긴 상업 영향: 손실 환산 가산액(이미 계산된 값), 일탈 후보 가격 영향 확인."""
    out = []
    for loss in queries.run_losses(conn, run_id):
        total = loss["total_usd"]
        out.append({"kind": "LOSS", "loss_calc_id": loss["loss_calc_id"], "item_id": None,
                    "judgment_id": None, "product_code": loss["product_code"],
                    "total_usd": float(total) if total is not None else None,
                    "is_assumed": loss["is_assumed"],
                    "text": None, "locations": loss["locations"]})
    for item in queries.run_outputs(conn, run_id, "DEVIATION"):
        if item["status"] == "REMOVED":
            continue
        judgment = next((s["judgment_id"] for s in item["sources"] if s["judgment_id"]), None)
        out.append({"kind": "DEVIATION", "loss_calc_id": None, "item_id": item["item_id"],
                    "judgment_id": judgment, "product_code": None, "total_usd": None,
                    "is_assumed": item["is_assumed"], "text": item["text_draft"],
                    "locations": item["locations"]})
    return out


def cost_summary(conn: psycopg.Connection, run_id: int) -> dict:
    return {"conditions": cost_conditions(conn, run_id),
            "impacts": commercial_impacts(conn, run_id)}
