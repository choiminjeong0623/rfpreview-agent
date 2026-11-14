"""FR-15 현장 이력 연결. 실행할 때는 요구–고장 연결표를 조회만 한다 (코드, CR-01).

요구사항 원문에 연결표 항목키의 같은 뜻 표현이 있고, 그 요구의 설비 종류가 연결표 줄의 적용 설비에
들면 그 줄의 고장(fault_catalog)을 붙인다. 연결표에 없는 항목은 연결하지 않는다.
AI는 짝을 짓지 않는다.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

import psycopg
from psycopg.rows import dict_row

from rfp_agent.pipeline.judge import _parts, _section_titles
from rfp_agent.pipeline.selection import (
    BREAKER,
    BREAKER_TABLE,
    GIS,
    INSTRUMENT,
    INSTRUMENT_TABLE,
    SWITCHGEAR,
    SWITCHGEAR_TABLE,
    TRANSFORMER,
    TRANSFORMER_TABLE,
)
from rfp_agent.pipeline.structure import normalize

# 요구사항의 설비 종류 코드 (연결표 "적용 설비" 칸에 쓴다)
EQUIPMENT_KINDS = {"GIS", "BREAKER", "SWITCHGEAR", "TRANSFORMER", "INSTRUMENT"}
# 목차가 통째로 요구 한 줄로 뽑힌 경우("1. Scope ........ 4 2. …")는 요구가 아니다
TOC_LEADERS = re.compile(r"\.{5,}\s*\d+")

REQUIREMENTS_SQL = """
    SELECT r.requirement_id, r.text_raw, r.section_id, d.file_no, d.file_name,
           t.table_name, t.table_id, tr.row_id,
           (SELECT min(l.line_start) FROM requirement_location rl
            JOIN source_location l ON l.location_id = rl.location_id
            WHERE rl.requirement_id = r.requirement_id) AS line_start
    FROM requirement r
    JOIN run_document rd ON rd.document_id = r.document_id AND rd.run_id = %(run)s
    JOIN document d ON d.document_id = r.document_id
    LEFT JOIN table_row tr ON tr.row_id = r.row_id
    LEFT JOIN doc_table t ON t.table_id = tr.table_id
    WHERE r.req_kind = 'REQUIREMENT'
      AND EXISTS (SELECT 1 FROM requirement_location rl
                  WHERE rl.requirement_id = r.requirement_id)
      AND (r.dedup_of IS NULL OR NOT EXISTS (
            SELECT 1 FROM requirement x JOIN run_document xd ON xd.document_id = x.document_id
            WHERE x.requirement_id = r.dedup_of AND xd.run_id = %(run)s))
    ORDER BY d.file_no, line_start, r.requirement_id"""


@dataclass
class FaultLink:
    fault_link_id: int
    item_key: str
    name_ko: str
    family: str
    fault_id: str
    symptom: str
    root_cause: str
    action: str
    kinds: set[str]
    cases: int                      # 의심 사례를 뺀 해결 사례 수
    suspects: int
    patterns: list[re.Pattern] = field(default_factory=list)


@dataclass
class FieldMatch:
    link: FaultLink
    requirement_id: int             # 대표 요구 (파일 번호·행이 가장 앞선 것)
    file_no: int
    line_start: int
    count: int                      # 같은 항목·같은 설비 종류 요구 수
    file_nos: list[int]


def alias_pattern(alias: str) -> re.Pattern:
    """낱말 경계로 찾는다 ("PD"가 다른 낱말 속에서 잡히지 않게). 영어 복수형도 같은 뜻."""
    return re.compile(rf"(?<![a-z0-9]){re.escape(normalize(alias).lower())}(?:e?s)?(?![a-z0-9])")


def load_links(conn: psycopg.Connection) -> list[FaultLink]:
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            """SELECT l.fault_link_id, l.item_key, k.name_ko, l.product_family AS family,
                      l.fault_id, f.symptom, f.root_cause, f.action, l.equipment_kinds,
                      (SELECT count(*) FROM resolution_case c
                       WHERE c.fault_id = l.fault_id AND c.suspect_reason IS NULL) AS cases,
                      (SELECT count(*) FROM resolution_case c
                       WHERE c.fault_id = l.fault_id AND c.suspect_reason IS NOT NULL)
                          AS suspects
               FROM fault_link l JOIN fault_catalog f ON f.fault_id = l.fault_id
               JOIN item_key k ON k.item_key = l.item_key AND k.active
               ORDER BY l.fault_link_id""").fetchall()
        aliases: dict[str, list[str]] = {}
        for key, alias in conn.execute("SELECT item_key, alias_text FROM item_alias "
                                       "ORDER BY item_key, alias_text"):
            aliases.setdefault(key, []).append(alias)
    links = []
    for r in rows:
        kinds = set(r.pop("equipment_kinds"))
        link = FaultLink(**r, kinds=kinds)
        link.patterns = [alias_pattern(a) for a in aliases.get(link.item_key, [])]
        links.append(link)
    return links


def kind_of(text: str | None, table: bool = False) -> str | None:
    """글 하나에서 설비 종류를 찾는다. 표 이름이면 표 이름 규칙(-CB, TR …)도 본다."""
    if not text:
        return None
    if INSTRUMENT.search(text) or (table and INSTRUMENT_TABLE.search(text)):
        return "INSTRUMENT"
    if GIS.search(text):
        return "GIS"
    if BREAKER.search(text) or (table and BREAKER_TABLE.search(text)):
        return "BREAKER"
    if TRANSFORMER.search(text) or (table and TRANSFORMER_TABLE.search(text)):
        return "TRANSFORMER"
    if SWITCHGEAR.search(text) or (table and SWITCHGEAR_TABLE.search(text)):
        return "SWITCHGEAR"
    return None


def equipment_kind(own: str | None, table_name: str | None, part_title: str | None,
                   section_titles: Iterable[str], file_name: str | None) -> str | None:
    """요구 문장 → 표 이름·구분 제목 → 속한 절부터 위 절 → 문서 이름 순서로 처음 찾은 종류."""
    for text, table in ((own, False), (table_name, True), (part_title, False),
                        *((t, False) for t in section_titles), (file_name, False)):
        if kind := kind_of(text, table):
            return kind
    return None


def find_matches(conn: psycopg.Connection, run_id: int) -> list[FieldMatch]:
    """연결표 줄마다 이 실행의 요구사항 중 이어지는 것을 찾는다. 줄마다 대표 요구 하나."""
    links = load_links(conn)
    if not links:
        return []
    with conn.cursor(row_factory=dict_row) as cur:
        reqs = cur.execute(REQUIREMENTS_SQL, {"run": run_id}).fetchall()
    parts = _parts(conn, list({r["table_id"] for r in reqs if r["table_id"]}))
    titles = _section_titles(conn, {r["section_id"] for r in reqs if r["section_id"]})
    found: dict[int, list[dict]] = {}
    for r in reqs:
        if TOC_LEADERS.search(r["text_raw"]):
            continue
        text = normalize(r["text_raw"]).lower()
        hits = [link for link in links if any(p.search(text) for p in link.patterns)]
        if not hits:
            continue
        kind = equipment_kind(r["text_raw"], r["table_name"],
                              parts.get(r["row_id"], ("", ""))[1] if r["row_id"] else None,
                              titles.get(r["section_id"], []), r["file_name"])
        for link in hits:
            if kind in link.kinds:
                found.setdefault(link.fault_link_id, []).append(r)
    matches = []
    for link in links:
        if rows := found.get(link.fault_link_id):
            first = rows[0]
            matches.append(FieldMatch(link, first["requirement_id"], first["file_no"],
                                      first["line_start"], len(rows),
                                      sorted({r["file_no"] for r in rows})))
    return matches
