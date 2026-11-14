"""요구사항 정답지: 넣기·공급사 답안으로 만들기·K1·K2·K3·K10 채점 (add-requirement-answer-key, B1).

정답 줄은 요구사항(REQUIREMENT, 값·단위 선택) 또는 위험 조건 종류
(BLANKET·OPEN_SCOPE·VALUE_MISMATCH).
채점은 코드로만(CR-01), 같은 입력이면 같은 점수(CR-11), 값은 단위 환산 없이(CR-10).
"""

import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path

import psycopg

RISK_KINDS = ("BLANKET", "OPEN_SCOPE", "VALUE_MISMATCH")
EXPECTED = ("REQUIREMENT", *RISK_KINDS)
MARK_HEADER = "C: Complied"
MARKS = ("C", "D", "E")
MIN_CONTAINED = 30          # 한쪽이 다른 쪽을 품을 때 짧은 쪽 최소 글자 수
MIN_CLAUSE = 15             # 공급사 답안 조항 줄 최소 글자 수

COLUMNS = {
    "row_no": ("번호", "row_no"),
    "text": ("text", "원문"),
    "expected": ("expected", "정답"),
    "value": ("value", "값"),
    "unit": ("unit", "단위"),
    "note": ("note", "메모"),
}


def normalize(text: str | None) -> str:
    return " ".join((text or "").split()).lower()


def same_line(key: str, req: str) -> bool:
    """정답 줄(key)과 시스템 요구사항(req)이 같은 줄인가. 둘 다 normalize한 글자.

    같거나, 한쪽이 다른 쪽을 품고 짧은 쪽이 30자 이상이거나, 표 줄 칸(" / ") 하나와 같으면 같다.
    """
    if not key or not req:
        return False
    if key == req:
        return True
    short, long_ = (key, req) if len(key) <= len(req) else (req, key)
    if len(short) >= MIN_CONTAINED and short in long_:
        return True
    return key in (part.strip() for part in req.split(" / "))


def _cell(row: dict, name: str) -> str:
    for col in COLUMNS[name]:
        if col in row and row[col] is not None:
            return row[col].strip()
    return ""


def new_key(conn: psycopg.Connection, name: str, made_by: str, doc_name: str | None) -> int:
    """요구사항 정답지 머리를 넣거나(같은 이름이면) 바꾸고 줄을 비운다."""
    key_id = conn.execute(
        """INSERT INTO answer_key (key_name, key_kind, made_by, doc_name)
           VALUES (%s, 'REQ', %s, %s)
           ON CONFLICT (key_name) DO UPDATE SET key_kind = 'REQ', made_by = EXCLUDED.made_by,
                  doc_name = EXCLUDED.doc_name, created_at = now()
           RETURNING key_id""", (name, made_by, doc_name)).fetchone()[0]
    conn.execute("DELETE FROM answer_key_row WHERE key_id = %s", (key_id,))
    return key_id


def _add_row(conn, key_id: int, row_no: int, text: str, expected: str, value: str | None,
             unit: str | None, note: str | None, human: bool) -> None:
    conn.execute(
        """INSERT INTO answer_key_row (key_id, row_no, text_raw, expected, value_raw, unit_raw,
                                       human_checked, note)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
        (key_id, row_no, text, expected, value or None, unit or None, human, note or None))


def load_req_key(conn: psycopg.Connection, path: Path, name: str, doc_name: str | None,
                 human: bool = False):
    """요구사항 정답지 CSV(번호, text, expected, value, unit, note)를 넣는다."""
    from rfp_agent.pipeline.evaluation import LoadReport

    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    key_id = new_key(conn, name, "HUMAN" if human else "CLAUDE_DRAFT", doc_name)
    report = LoadReport(key_id, 0, 0)
    for i, row in enumerate(rows, start=1):
        no = _cell(row, "row_no") or str(i)
        text, expected = _cell(row, "text"), _cell(row, "expected").upper()
        if not text:
            report.skipped.append(f"{no}번: 원문이 비었습니다")
            continue
        if expected not in EXPECTED:
            report.skipped.append(f"{no}번: 정답 종류가 아닙니다 ({expected or '빈칸'})")
            continue
        _add_row(conn, key_id, int(no) if no.isdigit() else i, text, expected,
                 _cell(row, "value"), _cell(row, "unit"), _cell(row, "note"), human)
        report.rows += 1
        report.human_checked += human
    conn.commit()
    return report


def supplier_rows(path: Path) -> list[tuple[str, str | None]] | None:
    """공급사 답안 docx의 표시 표에서 (조항 원문, 표시) 줄. 표시 머리가 없으면 None.

    구조 단계 코드를 쓰지 않고 표를 직접 읽는다(채점 대상과 정답이 같은 코드에서 나오지 않게).
    """
    from docx import Document

    doc = Document(str(path))
    texts = [p.text for p in doc.paragraphs]
    rows: list[list[str]] = []
    for table in doc.tables:
        for tr in table.rows:
            seen: set[int] = set()
            cells = []
            for cell in tr.cells:                   # 병합 칸은 한 번만
                if id(cell._tc) in seen:
                    continue
                seen.add(id(cell._tc))
                cells.append(cell.text.strip())
            rows.append(cells)
            texts.extend(cells)
    if not any(MARK_HEADER in t for t in texts):
        return None
    out: dict[str, tuple[str, str | None]] = {}
    for cells in rows:
        text = max(cells, key=len) if cells else ""
        if MARK_HEADER in text or len(text) < MIN_CLAUSE or not any(c.islower() for c in text):
            continue                                # 표시 머리·짧은 줄·제목 줄
        marks = [c for c in cells if c in MARKS]
        out.setdefault(normalize(text), (" ".join(text.split()), marks[0] if marks else None))
    return list(out.values())


def make_supplier_key(conn: psycopg.Connection, path: Path, name: str):
    """공급사 답안 docx로 요구사항 정답지를 만든다(코드 자동). 원문은 DB에만 넣는다."""
    from rfp_agent.pipeline.evaluation import LoadReport
    from rfp_agent.pipeline.review import ReviewError

    rows = supplier_rows(path)
    if rows is None:
        raise ReviewError(
            400, f"공급사 답안 문서가 아닙니다: 표시 머리 \"{MARK_HEADER}\"가 없습니다.")
    key_id = new_key(conn, name, "AUTO", path.stem)
    for no, (text, mark) in enumerate(rows, start=1):
        _add_row(conn, key_id, no, text, "REQUIREMENT", None, None,
                 f"공급사 표시 {mark}" if mark else None, False)
    conn.commit()
    return LoadReport(key_id, len(rows), 0)


def _number(text: str) -> Decimal | None:
    try:
        return Decimal(text.strip())
    except (InvalidOperation, AttributeError):
        return None


def _value_ok(value: str, unit: str | None, got: list[tuple]) -> bool:
    """정답 값·단위와 같은 시스템 값이 있나.

    숫자면 숫자로, 아니면 원문 글자로 비교한다. 단위는 글자 그대로(CR-10).
    """
    want = _number(value)
    unit = (unit or "").strip()
    for raw, num, got_unit in got:
        if (got_unit or "").strip() != unit:
            continue
        if want is not None and num is not None and Decimal(num) == want:
            return True
        if want is None and normalize(raw) == normalize(value):
            return True
    return False


def scope_documents(conn: psycopg.Connection, run_ids: list[int],
                    doc_name: str | None) -> list[int]:
    """고른 검토의 문서 중 파일 이름에 대상 문서 이름이 든 것."""
    docs = conn.execute(
        """SELECT DISTINCT d.document_id, d.file_name FROM run_document rd
             JOIN document d USING (document_id)
            WHERE rd.run_id = ANY(%s) ORDER BY d.document_id""", (run_ids,)).fetchall()
    want = normalize(doc_name)
    return [i for i, file_name in docs if not want or want in normalize(file_name)]


def scores(conn: psycopg.Connection, run_ids: list[int], key_id: int, metric) -> tuple[list, dict]:
    """K1·K2·K3·K10과 자세한 수. metric은 evaluation._metric."""
    from rfp_agent.pipeline.evaluation import _pct

    doc_name = conn.execute("SELECT doc_name FROM answer_key WHERE key_id = %s",
                            (key_id,)).fetchone()[0]
    docs = scope_documents(conn, run_ids, doc_name)
    reqs = [(rid, normalize(text)) for rid, text in conn.execute(
        """SELECT requirement_id, text_raw FROM requirement
            WHERE req_kind = 'REQUIREMENT' AND document_id = ANY(%s)
            ORDER BY requirement_id""", (docs,))]
    values: dict[int, list[tuple]] = {}
    for rid, raw, num, unit in conn.execute(
            "SELECT requirement_id, raw_text, num_value, unit_raw FROM req_value "
            "WHERE requirement_id = ANY(%s) ORDER BY value_id", ([r for r, _ in reqs],)):
        values.setdefault(rid, []).append((raw, num, unit))
    answers = conn.execute(
        "SELECT text_raw, expected, value_raw, unit_raw FROM answer_key_row WHERE key_id = %s "
        "ORDER BY row_no", (key_id,)).fetchall()
    req_rows = [(normalize(t), v, u) for t, e, v, u in answers if e == "REQUIREMENT"]
    risk_rows = [(normalize(t), e) for t, e, _, _ in answers if e != "REQUIREMENT"]

    found = value_den = value_hit = 0
    for text, value, unit in req_rows:
        hits = [rid for rid, req in reqs if same_line(text, req)]
        found += bool(hits)
        if hits and value:
            value_den += 1
            value_hit += any(_value_ok(value, unit, values.get(rid, [])) for rid in hits)
    correct = sum(any(same_line(text, req) for text, _, _ in req_rows) for _, req in reqs)

    risks: dict[str, list[list[str]]] = {}
    for kind, members in conn.execute(
            """SELECT f.risk_kind, array_agg(q.text_raw ORDER BY q.requirement_id)
                 FROM risk_flag f JOIN risk_flag_member m USING (risk_id)
                 JOIN requirement q USING (requirement_id)
                WHERE f.run_id = ANY(%s) AND q.document_id = ANY(%s)
                GROUP BY f.risk_id ORDER BY f.risk_id""", (run_ids, docs)):
        risks.setdefault(kind, []).append([normalize(t) for t in members])
    risk_found = sum(any(same_line(text, m) for group in risks.get(kind, []) for m in group)
                     for text, kind in risk_rows)

    scope = f"대상 문서 {len(docs)}개" + (f" (\"{doc_name}\")" if doc_name else "")
    n_req, n_risk = len(req_rows), len(risk_rows)
    items = [
        metric("K1", "요구사항 추출 재현율", "정답 요구사항 줄 중 시스템이 찾은 비율", "%",
               _pct(found, n_req), found, n_req, note=scope),
        metric("K2", "요구사항 추출 정확도", "대상 문서에서 시스템이 찾은 요구사항 중 정답인 비율",
               "%", _pct(correct, len(reqs)), correct, len(reqs), note=scope),
        metric("K3", "값·단위 정확도",
               "값이 있는 정답 줄 중 찾은 줄의 값·단위가 같은 비율(환산 없음)", "%",
               _pct(value_hit, value_den), value_hit, value_den),
        metric("K10", "위험 조건 탐지 재현율", "정답 위험 조건 중 같은 종류 후보로 찾은 비율", "%",
               _pct(risk_found, n_risk), risk_found, n_risk),
    ]
    detail = {"documents": len(docs), "requirement_rows": n_req, "found": found,
              "system_requirements": len(reqs), "correct": correct, "value_rows": value_den,
              "value_hit": value_hit, "risk_rows": n_risk, "risk_found": risk_found}
    return items, detail
