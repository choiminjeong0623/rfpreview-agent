"""판정 정답지: 넣기·K5-정답지·K6-정답지 채점 (add-eval-demo).

정답 줄은 요구사항 원문, 정답 판정, 비교 제품 코드(비면 보지 않음), 애매함.
줄 맞추기는 요구사항 정답지와 같은 규칙(req_eval.same_line), 대상 문서도 같다.
채점은 코드로만(CR-01), 같은 입력이면 같은 점수(CR-11).
"""

import csv
from pathlib import Path

import psycopg

from rfp_agent.llm.tasks import JUDGMENT_RESULTS
from rfp_agent.pipeline import req_eval
from rfp_agent.pipeline.req_eval import normalize, same_line

DEVIATION = "DEVIATION_CANDIDATE"
NONE = "NONE"                      # 정답 줄과 맞는 판정이 없음
COLUMNS = {
    "row_no": ("번호", "row_no"),
    "text": ("text", "원문"),
    "expected": ("expected", "정답"),
    "product": ("product_code", "비교 제품"),
    "ambiguous": ("ambiguous", "애매함(Y)"),
    "note": ("note", "메모"),
}


def _cell(row: dict, name: str) -> str:
    for col in COLUMNS[name]:
        if col in row and row[col] is not None:
            return row[col].strip()
    return ""


def load_judge_key(conn: psycopg.Connection, path: Path, name: str, doc_name: str | None,
                   human: bool = False):
    """판정 정답지 CSV(번호, text, expected, product_code, ambiguous, note)를 넣는다.

    정답 줄은 문서 순서로 적는다: 글자가 같은 줄(다른 표의 같은 항목)은 순서로 짝짓는다.
    """
    from rfp_agent.pipeline.evaluation import LoadReport

    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    key_id = conn.execute(
        """INSERT INTO answer_key (key_name, key_kind, made_by, doc_name)
           VALUES (%s, 'JUDGE', %s, %s)
           ON CONFLICT (key_name) DO UPDATE SET key_kind = 'JUDGE', made_by = EXCLUDED.made_by,
                  doc_name = EXCLUDED.doc_name, created_at = now()
           RETURNING key_id""", (name, "HUMAN" if human else "CLAUDE_DRAFT", doc_name)
    ).fetchone()[0]
    conn.execute("DELETE FROM answer_key_row WHERE key_id = %s", (key_id,))
    report = LoadReport(key_id, 0, 0)
    for i, row in enumerate(rows, start=1):
        no = _cell(row, "row_no") or str(i)
        text, expected = _cell(row, "text"), _cell(row, "expected").upper()
        if not text:
            report.skipped.append(f"{no}번: 원문이 비었습니다")
            continue
        if expected not in JUDGMENT_RESULTS:
            report.skipped.append(f"{no}번: 판정 값이 아닙니다 ({expected or '빈칸'})")
            continue
        conn.execute(
            """INSERT INTO answer_key_row (key_id, row_no, text_raw, expected, product_code,
                                           ambiguous, human_checked, note)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (key_id, int(no) if no.isdigit() else i, text, expected,
             _cell(row, "product") or None, _cell(row, "ambiguous").upper() == "Y", human,
             _cell(row, "note") or None))
        report.rows += 1
        report.human_checked += human
    conn.commit()
    return report


def scores(conn: psycopg.Connection, run_ids: list[int], key_id: int, metric) -> tuple[list, dict]:
    """K5-정답지·K6-정답지와 정답 × 시스템 건수 표. metric은 evaluation._metric."""
    from rfp_agent.pipeline.evaluation import _pct

    doc_name = conn.execute("SELECT doc_name FROM answer_key WHERE key_id = %s",
                            (key_id,)).fetchone()[0]
    docs = req_eval.scope_documents(conn, run_ids, doc_name)
    judged = [(jid, normalize(text), result, product) for jid, text, result, product in
              conn.execute(
                  """SELECT j.judgment_id, q.text_raw, j.result, j.product_code
                       FROM judgment j JOIN requirement q USING (requirement_id)
                      WHERE j.run_id = ANY(%s) AND j.is_current AND q.document_id = ANY(%s)
                      ORDER BY q.requirement_id, j.judgment_id""", (run_ids, docs))]
    answers = conn.execute(
        "SELECT text_raw, expected, product_code, ambiguous FROM answer_key_row "
        "WHERE key_id = %s ORDER BY row_no", (key_id,)).fetchall()
    used: set[int] = set()
    hit = den = dev_hit = dev_den = not_found = amb = amb_hit = 0
    table: dict[tuple[str, str], int] = {}
    for text, expected, product, ambiguous in answers:
        want = normalize(text)
        match = next((j for j in judged if j[0] not in used and same_line(want, j[1])), None)
        got, got_product = (NONE, None) if match is None else (match[2], match[3])
        if match is None:
            not_found += 1
        else:
            used.add(match[0])
        ok = got == expected and (not product or expected == "NEEDS_REVIEW"
                                  or got_product == product)
        if ambiguous:
            amb += 1
            amb_hit += ok
            continue
        table[(expected, got)] = table.get((expected, got), 0) + 1
        den += 1
        hit += ok
        if expected == DEVIATION:
            dev_den += 1
            dev_hit += got == DEVIATION
    notes = [f"대상 문서 {len(docs)}개"]
    if not_found:
        notes.append(f"맞는 판정이 없는 줄 {not_found}개(틀린 것으로 셈)")
    if amb:
        notes.append(f"애매한 줄 {amb_hit}/{amb} 따로")
    items = [
        metric("K5-KEY", "판정 정확도(정답지)",
               "판정 정답지 줄 중 시스템 판정(과 비교 제품)이 같은 비율", "%",
               _pct(hit, den), hit, den, note=" · ".join(notes)),
        metric("K6-KEY", "일탈 재현율(정답지)",
               "정답이 일탈 후보인 줄 중 시스템도 일탈 후보로 낸 비율", "%",
               _pct(dev_hit, dev_den), dev_hit, dev_den),
    ]
    detail = {"rows": len(answers), "matched": len(answers) - not_found, "not_found": not_found,
              "ambiguous": amb, "ambiguous_hit": amb_hit,
              "table": [{"expected": e, "system": g, "count": n}
                        for (e, g), n in sorted(table.items())]}
    return items, detail
