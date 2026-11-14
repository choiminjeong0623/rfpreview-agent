"""원문 앞뒤 줄 (change add-judgment-view, 판정 상세 화면 SCR-08-12).

줄 번호는 분석 때와 같은 방법으로 다시 만든다: docx 블록을 줄로 펴고(docx_reader),
팀 추출 txt가 있으면 그 줄 번호에 맞춘다(line_map, process_document와 같은 조건).
그래서 저장한 원문 위치(line_start)와 돌려주는 줄 번호가 같다 (CR-11).
올린 파일이 없으면 DB에 남은 줄(절 제목·표 행·요구 문장)만 돌려주고 partial로 알린다.
"""

from collections import OrderedDict
from pathlib import Path
from threading import Lock

import psycopg

from rfp_agent.pipeline.line_map import map_lines
from rfp_agent.pipeline.reader import read_document

MAX_LINES = 40
_CACHE_SIZE = 8
_cache: OrderedDict[tuple[str, float, str | None], dict[int, str]] = OrderedDict()
_lock = Lock()


class LineRangeError(ValueError):
    """줄 범위가 틀림 (1 이상, 끝 ≥ 시작, 최대 40줄)."""


def check_range(start: int, end: int) -> None:
    if start < 1 or end < start:
        raise LineRangeError("줄 범위가 틀렸습니다. 시작은 1 이상, 끝은 시작 이상이어야 합니다.")
    if end - start + 1 > MAX_LINES:
        raise LineRangeError(f"줄은 한 번에 {MAX_LINES}줄까지 볼 수 있습니다.")


def file_lines(path: Path, txt_dir: Path | None) -> dict[int, str]:
    """docx 파일의 {줄 번호: 글}. 같은 (경로, 수정 시각, txt)는 최근 8개를 다시 쓴다."""
    txt = txt_dir / f"{path.stem}.txt" if txt_dir else None
    txt = txt if txt and txt.exists() else None
    key = (str(path), path.stat().st_mtime, str(txt) if txt else None)
    with _lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    blocks = read_document(path)
    if txt:
        blocks, _ = map_lines(blocks, txt)
    lines: dict[int, str] = {}
    for b in blocks:
        for k, text in enumerate(b.text.split("\n")):
            # txt에 맞춘 블록은 번호가 겹칠 수 있다. 앞 블록을 남긴다 (분석이 먼저 본 줄)
            lines.setdefault(b.line_no + k, text)
    with _lock:
        _cache[key] = lines
        while len(_cache) > _CACHE_SIZE:
            _cache.popitem(last=False)
    return lines


def _stored_lines(conn: psycopg.Connection, document_id: int, start: int,
                  end: int) -> dict[int, str]:
    """DB에 남은 줄. 같은 줄 번호면 절 제목 → 표 행 → 요구 문장 순서로 하나만."""
    out: dict[int, str] = {}
    for line_no, title in conn.execute(
            "SELECT line_start, concat_ws(' ', section_no, title) FROM section "
            "WHERE document_id = %s AND line_start BETWEEN %s AND %s", (document_id, start, end)):
        out.setdefault(line_no, title)
    for row in conn.execute(
            "SELECT tr.line_no, tr.item_no, tr.item_name_raw, tr.unit_raw, tr.required_raw, "
            "tr.warranted_raw FROM table_row tr JOIN doc_table t USING (table_id) "
            "WHERE t.document_id = %s AND tr.line_no BETWEEN %s AND %s ORDER BY tr.row_order",
            (document_id, start, end)):
        out.setdefault(row[0], " | ".join(c or "" for c in row[1:]))
    for line_no, text in conn.execute(
            "SELECT l.line_start, q.text_raw FROM requirement q "
            "JOIN requirement_location rl USING (requirement_id) "
            "JOIN source_location l USING (location_id) "
            "WHERE l.document_id = %s AND l.line_start BETWEEN %s AND %s "
            "ORDER BY l.line_start, q.requirement_id", (document_id, start, end)):
        out.setdefault(line_no, text)
    return out


def document_lines(conn: psycopg.Connection, run_id: int, file_no: int, start: int, end: int,
                   txt_dir: Path | None) -> dict | None:
    """그 검토 문서의 줄 범위. 검토에 없는 문서면 None."""
    check_range(start, end)
    doc = conn.execute(
        "SELECT d.document_id, d.file_name, d.source_path FROM run_document rd "
        "JOIN document d USING (document_id) WHERE rd.run_id = %s AND d.file_no = %s",
        (run_id, file_no)).fetchone()
    if doc is None:
        return None
    document_id, file_name, source_path = doc
    path = Path(source_path) if source_path else None
    if path and path.is_file():
        lines, partial = file_lines(path, txt_dir), False
        picked = {n: lines[n] for n in range(start, end + 1) if n in lines}
    else:
        picked, partial = _stored_lines(conn, document_id, start, end), True
    return {
        "file_no": file_no, "file_name": file_name, "line_from": start, "line_to": end,
        "partial": partial,
        "lines": [{"line_no": n, "text": picked[n]} for n in sorted(picked)],
    }
