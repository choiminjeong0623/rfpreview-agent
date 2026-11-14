"""문서 읽기 점검 (SCR-08-2): 시스템이 제대로 읽지 못한 곳을 모아 사람이 원문을 직접 확인하게 한다.

점검 줄은 저장된 처리 결과(표 칸 역할, 그림 위치, 단위 없는 값, 절 번호)에서 코드로 만든다 (CR-01).
같은 입력이면 같은 줄이 같은 순서로 나온다 (CR-11). 사람이 확인한 기록만 read_check에 남긴다.
"""

import re

import psycopg
from psycopg.rows import dict_row

from rfp_agent.pipeline.pdf_reader import page_of
from rfp_agent.pipeline.review import ReviewError, _user_role, default_user, log, require_stage

KINDS = ("표", "그림", "단위", "위치")
# 여러 단계 절 번호(6.3, 7.4.2)는 한 문서에서 두 번 나오면 안 된다.
# "1)"·"a." 같은 목록 번호는 되풀이되므로 보지 않는다
DOTTED = re.compile(r"^\d+(\.\d+)+\.?$")


def _lines(a: int | None, b: int | None) -> str:
    if a is None:
        return ""
    return f"{a}행" if b is None or a == b else f"{a}~{b}행"


def _join(*parts: str | None) -> str:
    return " · ".join(p for p in parts if p)


def _section(no: str | None, title: str | None) -> str | None:
    if no:
        return f"{no}절"
    return title[:40] if title else None


def _row(key: str, kind: str, what: str, doc: dict, loc: str, line: int | None, problem: str,
         todo: str) -> dict:
    page = page_of(doc.get("page_starts"), line)                 # PDF 쪽 (add-pdf-page-location)
    loc = _join(f"{page}쪽" if page else None, loc)
    return {"key": key, "kind": kind, "what": what, "document_id": doc["document_id"],
            "file_name": doc["file_name"], "loc": loc, "line": line, "problem": problem,
            "todo": todo}


def _documents(cur, run_id: int) -> dict[int, dict]:
    rows = cur.execute(
        """SELECT d.document_id, d.file_no, d.file_name, d.readable, d.page_starts
           FROM run_document rd
           JOIN document d USING (document_id) WHERE rd.run_id = %s ORDER BY d.file_no""",
        (run_id,)).fetchall()
    return {r["document_id"]: r for r in rows}


def _tables(cur, docs: dict[int, dict]) -> list[dict]:
    rows = cur.execute(
        """SELECT t.table_id, t.document_id, t.table_name, s.section_no, s.title,
                  min(r.line_no) AS a, max(r.line_no) AS b, count(r.row_id) AS n
           FROM doc_table t LEFT JOIN section s USING (section_id)
           LEFT JOIN table_row r USING (table_id)
           WHERE t.document_id = ANY(%s) AND t.role_flag
           GROUP BY t.table_id, s.section_no, s.title ORDER BY t.document_id, min(r.line_no)""",
        (list(docs),)).fetchall()
    return [_row(f"T-{t['table_id']}", "표", "표 칸을 읽지 못함", docs[t["document_id"]],
                 _join(t["table_name"] or _section(t["section_no"], t["title"]) or "표",
                       _lines(t["a"], t["b"])), t["a"],
                 f"머리글 행을 찾지 못해 표 {t['n']}행의 칸 역할(항목·단위·요구값)을 "
                 "정하지 못했습니다. "
                 "이 표의 요구사항은 판정에 없을 수 있습니다.",
                 "원문 표에서 요구값을 직접 확인")
            for t in rows]


def _figures(cur, docs: dict[int, dict]) -> list[dict]:
    out = [_row(f"D-{d['document_id']}", "그림", "문서를 읽지 않음", d, "문서 전체", None,
                "글자를 읽을 수 없는 문서(스캔·그림)라 요구사항을 뽑지 않았습니다.",
                "원문을 직접 열어 요구사항이 있는지 확인")
           for d in docs.values() if not d["readable"]]
    rows = cur.execute(
        """SELECT f.figure_id, f.document_id, f.line_no, f.caption, s.section_no, s.title
           FROM doc_figure f LEFT JOIN section s USING (section_id)
           WHERE f.document_id = ANY(%s) ORDER BY f.document_id, f.line_no, f.figure_id""",
        (list(docs),)).fetchall()
    out += [_row(f"F-{f['figure_id']}", "그림", "그림 속 글자는 읽지 않음", docs[f["document_id"]],
                 _join(f["caption"] or _section(f["section_no"], f["title"]) or "그림",
                       f"{f['line_no']}행"), f["line_no"],
                 "그림 안에 정격값이나 치수가 적혀 있을 수 있습니다. 본문 값과 다를 수 있습니다.",
                 "그림의 값이 본문과 같은지 확인")
            for f in rows]
    return out


def _units(cur, docs: dict[int, dict]) -> list[dict]:
    """단위 없는 값은 표 하나(또는 절 하나)마다 한 줄로 묶는다."""
    rows = cur.execute(
        """SELECT q.document_id, r.table_id, t.table_name, q.section_id, s.section_no, s.title,
                  min(l.line_start) AS a, max(l.line_start) AS b, count(DISTINCT v.value_id) AS n,
                  (array_agg(v.raw_text ORDER BY l.line_start, v.value_id))[1] AS example,
                  array_agg(DISTINCT r.item_no) FILTER (WHERE r.item_no IS NOT NULL) AS items
           FROM req_value v JOIN requirement q USING (requirement_id)
           JOIN requirement_location ql USING (requirement_id)
           JOIN source_location l ON l.location_id = ql.location_id
                                 AND l.document_id = q.document_id
           LEFT JOIN table_row r ON r.row_id = q.row_id
           LEFT JOIN doc_table t ON t.table_id = r.table_id
           LEFT JOIN section s ON s.section_id = q.section_id
           WHERE q.document_id = ANY(%s) AND v.flag = 'UNIT_MISSING' AND q.dedup_of IS NULL
           GROUP BY q.document_id, r.table_id, t.table_name, q.section_id, s.section_no, s.title
           ORDER BY q.document_id, min(l.line_start)""",
        (list(docs),)).fetchall()
    merged: dict[tuple, dict] = {}
    for u in rows:                                   # 표 안의 값은 절이 달라도 표 하나로 합친다
        key = (u["document_id"], "T", u["table_id"]) if u["table_id"] else \
            (u["document_id"], "S", u["section_id"])
        m = merged.setdefault(key, {**u, "n": 0, "items": [], "b": u["b"]})
        m["n"] += u["n"]
        m["items"] += u["items"] or []
        m["b"] = max(m["b"], u["b"])
    out = []
    for (doc_id, scope, ref), u in merged.items():
        items = sorted(set(u["items"]), key=lambda s: (len(s), s))
        if scope == "T":
            where = u["table_name"] or "표"
            span = f"No. {items[0]}" if len(items) == 1 else \
                f"No. {items[0]}~{items[-1]}" if items else _lines(u["a"], u["b"])
        else:
            where = _section(u["section_no"], u["title"]) or "본문"
            span = _lines(u["a"], u["b"])
        out.append(_row(f"U-{doc_id}-{scope}{ref or 0}", "단위", "단위를 모름", docs[doc_id],
                        _join(where, span), u["a"],
                        f"값 {u['n']}개(예: \"{u['example']}\")에 단위가 없어 "
                        "제품값과 비교하지 않았습니다.",
                        "요구값의 단위를 원문에서 확인"))
    return out


def _places(cur, docs: dict[int, dict]) -> list[dict]:
    rows = cur.execute(
        """SELECT section_id, document_id, section_no, title, line_start, structure_flag
           FROM section WHERE document_id = ANY(%s) AND NOT is_toc
           ORDER BY document_id, line_start, section_id""", (list(docs),)).fetchall()
    out = []
    seen: dict[tuple[int, str], list[dict]] = {}
    for s in rows:
        if s["section_no"] and DOTTED.match(s["section_no"]):
            seen.setdefault((s["document_id"], s["section_no"].rstrip(".")), []).append(s)
    for s in rows:
        if s["structure_flag"]:
            out.append(_row(
                f"P-{s['section_id']}", "위치", "절 번호가 끊김", docs[s["document_id"]],
                _join(_section(s["section_no"], s["title"]), f"{s['line_start']}행"),
                s["line_start"], "앞 절 번호에서 이어지지 않아 앞뒤 절에 붙였습니다. "
                "이 절 요구사항의 위치가 틀릴 수 있습니다.", "원문에서 절 번호와 위치를 확인"))
        same = seen.get((s["document_id"], (s["section_no"] or "").rstrip(".")))
        if same and len(same) > 1 and same[0] is s:
            lines = "과 ".join(f"{x['line_start']}행" for x in same)
            no = s["section_no"].rstrip(".")
            out.append(_row(f"P-{s['document_id']}-{no}", "위치", "위치가 모호함",
                            docs[s["document_id"]], f"{no}절 · {lines}", s["line_start"],
                            f"같은 절 번호 {no}이(가) {len(same)}번 나옵니다. 요구사항 위치의 "
                            f"\"{no}절\"이 어느 쪽인지 원문으로 구분해야 합니다.",
                            f"어느 {no}절의 요구사항인지 확인"))
    return out


def read_checks(conn: psycopg.Connection, run_id: int) -> list[dict]:
    """점검 줄 목록. 표 → 그림 → 단위 → 위치 순서, 종류 안에서는 파일·줄 순서."""
    with conn.cursor(row_factory=dict_row) as cur:
        if cur.execute("SELECT 1 FROM review_run WHERE run_id = %s", (run_id,)).fetchone() is None:
            raise ReviewError(404, f"검토 실행 {run_id}이(가) 없습니다.")
        docs = _documents(cur, run_id)
        rows = _tables(cur, docs) + _figures(cur, docs) + _units(cur, docs) + _places(cur, docs) \
            if docs else []
        checked = {r["check_key"]: r for r in cur.execute(
            """SELECT c.check_key, u.user_name, c.checked_at FROM read_check c
               JOIN app_user u ON u.user_id = c.checked_by
               WHERE c.run_id = %s AND c.checked_at IS NOT NULL""", (run_id,))}
    for r in rows:
        c = checked.get(r["key"])
        r["checked_by"] = c["user_name"] if c else None
        r["checked_at"] = c["checked_at"] if c else None
    return rows


def unchecked(conn: psycopg.Connection, run_id: int) -> int:
    return sum(1 for r in read_checks(conn, run_id) if r["checked_at"] is None)


def set_checked(conn: psycopg.Connection, run_id: int, key: str, checked: bool,
                actor_id: int | None = None) -> dict:
    """점검 줄을 "직접 확인함"으로 표시하거나 되돌린다. 두 동작 모두 이력에 남긴다."""
    require_stage(conn, run_id, "ENGINEER_REVIEW")
    actor_id = actor_id or default_user(conn, "ENGINEER")
    _user_role(conn, actor_id)
    row = next((r for r in read_checks(conn, run_id) if r["key"] == key), None)
    if row is None:
        raise ReviewError(404, f"점검 줄 {key}이(가) 이 실행에 없습니다.")
    if (row["checked_at"] is not None) == checked:
        raise ReviewError(409, "이미 확인했습니다." if checked else "확인하지 않은 줄입니다.")
    label = f"{row['loc']} ({row['what']})"
    with conn.cursor(row_factory=dict_row) as cur:
        saved = cur.execute(
            """INSERT INTO read_check (run_id, check_key, label, checked_by, checked_at)
               VALUES (%(run)s, %(key)s, %(label)s, %(by)s, CASE WHEN %(on)s THEN now() END)
               ON CONFLICT (run_id, check_key) DO UPDATE SET label = EXCLUDED.label,
                 checked_by = EXCLUDED.checked_by, checked_at = EXCLUDED.checked_at
               RETURNING read_check_id, checked_at""",
            {"run": run_id, "key": key, "label": label, "by": actor_id, "on": checked}).fetchone()
    log(conn, run_id, "read_check", saved["read_check_id"], "CONFIRM" if checked else "UNDO",
        {"key": key, "checked": not checked}, {"key": key, "checked": checked}, None, actor_id)
    conn.commit()
    return next(r for r in read_checks(conn, run_id) if r["key"] == key)
