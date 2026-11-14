"""글자가 든 PDF를 docx와 같은 단락·표 행 블록으로 읽는다 (add-pdf-input).

쪽마다 표는 표 행으로, 표 밖 글자 줄은 줄 간격으로 묶어 단락으로 만든다. 줄 번호는 문서 처음부터
이어 센다. 쪽마다 같은 높이에 반복되는 머리말·꼬리말(쪽 번호 등)은 뺀다.
글자 층이 없는 쪽은 OCR 엔진이 있으면 OCR로 읽는다(add-ocr).
글자 쪽의 큰 그림은 그림 위치로 남기고 OCR하며, 도면 쪽(표제란)은 주기 줄만 읽고, 돌아간 글자는
읽지 않고 그림 위치로 알린다(update-pdf-drawings).
엔진이 없는 스캔 PDF나 열 수 없는 PDF는 블록 0개(판독 불가).
"""

import math
import re
from collections import Counter
from pathlib import Path

import pdfplumber

from rfp_agent.pipeline import ocr
from rfp_agent.pipeline.docx_reader import Block
from rfp_agent.pipeline.structure import MARK_LEGEND, heading_of

PARA_GAP = 1.5          # 쪽의 줄 간격을 모를 때: 줄 위아래 간격이 줄 높이의 이 배를 넘으면 새 단락
# 쪽마다 가장 흔한 줄 사이 간격을 단락 안 간격으로 보고, 그보다 이만큼 넓으면 새 단락
# (update-pdf-tables)
GAP_RATIO, GAP_MIN = 0.5, 2.0
EDGE = 0.05             # 쪽 위·아래 이 비율 안의 줄은 머리말·꼬리말 후보
# 번호로 시작하는 줄은 새 단락 ("1.", "1.1", "A.", "PART 1", "가.", "1)")
NUMBERED = re.compile(r"^\s*(?:PART\s+\d+|\d+(?:\.\d+)*\.?\s|[A-Z]\.\s|[가-힣]\.\s|\d+\)\s)")
# 글머리표로 시작하는 줄도 새 단락 (•·▪◦●○■□※, 기호 글꼴이 바꾼 \x80~\x9f·\uf0xx)
BULLET = re.compile(r"^\s*[•·▪◦●○■□※\x80-\x9f\uf020-\uf0ff]")


# 글자 쪽의 그림: 쪽 넓이의 이 비율 이상, 가로·세로 이 pt 이상 (로고·도장은 건너뜀)
FIGURE_AREA, FIGURE_MIN = 0.05, 72
# 도면 쪽: 표제란 낱말 두 가지가 함께 있으면 (update-pdf-drawings)
DRAWING_NO = re.compile(r"\b(?:DRAWING|DWG)[\s._]*NO\b", re.IGNORECASE)
SCALE = re.compile(r"\bSCALE\b", re.IGNORECASE)
TITLE = re.compile(r"^\s*TITLE\b", re.IGNORECASE)
NOTE = re.compile(r"^\s*NOTES?\b", re.IGNORECASE)     # 도면 주기 줄은 한 줄씩 단락
# 표제란 라벨 줄: 짧고, 문장으로 끝나지 않고, 요구 낱말이 없음 (update-pdf-drawing-guards)
LABEL_MAX = 30
OBLIGATION = re.compile(r"\b(?:shall|must)\b", re.IGNORECASE)
PROSE_LINES = 2                 # shall·must 줄이 이만큼 있으면 사양 본문 쪽 (도면 쪽 아님)
NUMBER = re.compile(DRAWING_NO.pattern + r"\.?\s*:?\s*([A-Z0-9][\w./-]*)", re.IGNORECASE)
ROTATED_DEG = 30                # 이 각도를 넘게 돈 글자만 뺀다 (기울임꼴은 읽음)
FIGURE_TEXT_CHARS = 50          # 그림 영역 안 글자층이 이만큼이면 OCR 안 함 [제안]


def _straight(obj: dict) -> bool:
    """가로로 읽을 글자인가. 가로 성분 a가 0 이하(세로·뒤집힘)이거나 30°를 넘게 돈 글자만 아니다.

    c만 있는 기울이기(기울임꼴을 기울여 그린 글자)는 가로 글자다. 글자가 아닌 개체는 그대로 둔다.
    """
    if obj.get("object_type") != "char":
        return True
    a, b = (obj.get("matrix") or (1, 0, 0, 1, 0, 0))[:2]
    return a > 0 and abs(math.degrees(math.atan2(b, a))) <= ROTATED_DEG


def _label(text: str) -> bool:
    """표제란 라벨 줄: 30자 이하, "."로 끝나지 않고 shall·must가 없음"""
    t = text.strip()
    return len(t) <= LABEL_MAX and not t.endswith(".") and not OBLIGATION.search(t)


def _drawing_page(tables, lines: list[dict]) -> bool:
    """표제란 증거(표 칸이나 라벨 줄의 DRAWING NO·SCALE)가 있고 요구 문장 줄이 적은 쪽"""
    if sum(1 for ln in lines if OBLIGATION.search(ln["text"])) >= PROSE_LINES:
        return False
    marks = [c for t in tables for row in t.extract() for c in row if c]
    marks += [ln["text"] for ln in lines if _label(ln["text"])]
    return any(DRAWING_NO.search(m) for m in marks) and any(SCALE.search(m) for m in marks)


def _inside(line: dict, boxes: list[tuple]) -> bool:
    mid = (line["top"] + line["bottom"]) / 2
    return any(x0 - 1 <= line["x0"] and line["x1"] <= x1 + 1 and top - 1 <= mid <= bottom + 1
               for x0, top, x1, bottom in boxes)


def _edge_key(line: dict, height: float) -> str | None:
    """머리말·꼬리말 후보면 (위치, 숫자를 지운 글자). 쪽 번호가 달라도 같은 줄로 본다."""
    if line["top"] > height * EDGE and line["bottom"] < height * (1 - EDGE):
        return None
    where = "top" if line["top"] <= height * EDGE else "bottom"
    return f"{where}|{re.sub(r'\d+', '#', line['text'].strip())}"


def _join(lines: list[str]) -> str:
    """접혀 넘어간 줄을 한 줄로 잇는다 (docx 단락처럼). 줄 끝 "-"로 끊긴 낱말은 붙인다."""
    text = lines[0]
    for line in lines[1:]:
        if re.search(r"[A-Za-z]-$", text) and line[:1].islower():
            text = text[:-1] + line
        else:
            text = f"{text} {line}"
    return text


def line_gap(lines: list[dict]) -> float | None:
    """쪽에서 가장 흔한 줄 사이 간격(1pt 단위)을 단락 안 간격으로 본다.

    그보다 넓은 간격(단락 사이)이 쪽에 따로 있을 때만 쓴다. 간격이 고르면(단락 사이를 띄우지 않은
    쪽) 무엇이 단락 사이인지 알 수 없어 None을 돌려주고 줄 높이 기준을 쓴다.
    """
    gaps = [round(b["top"] - a["bottom"]) for a, b in zip(lines, lines[1:], strict=False)
            if 0 <= b["top"] - a["bottom"] < 2 * (a["bottom"] - a["top"] or 1)]
    if len(gaps) < 2:
        return None
    common = Counter(gaps).most_common(1)[0][0]
    wider = any(g > common + max(GAP_MIN, common * GAP_RATIO) for g in gaps)
    return common if wider else None


def _paragraphs(lines: list[dict], gap: float | None = None) -> list[str]:
    """표 밖 글자 줄을 단락으로 묶는다. 단락 하나가 한 줄이다(줄 번호도 단락마다 하나).

    gap은 그 쪽의 단락 안 줄 간격(line_gap). 없으면 줄 높이로 정한다.
    """
    out: list[list[str]] = []
    prev = None
    for line in lines:
        height = line["bottom"] - line["top"] or 1
        limit = height * (PARA_GAP - 1) if gap is None else gap + max(GAP_MIN, gap * GAP_RATIO)
        new = prev is None or line["top"] - prev["bottom"] > limit or line.get("own") \
            or NUMBERED.match(line["text"]) or BULLET.match(line["text"])
        if new:
            out.append([line["text"]])
        else:
            out[-1].append(line["text"])
        prev = line
    return [_join(p) for p in out]


def _next_line(blocks: list[Block]) -> int:
    return blocks[-1].last_line + 1 if blocks else 1


def _add_paragraphs(blocks: list[Block], lines: list[dict], gap: float | None = None) -> None:
    # OCR 줄과 글자 층 줄은 섞지 않는다 (OCR 단락은 표시가 따로 붙는다)
    groups: list[list[dict]] = []
    for line in lines:
        if groups and groups[-1][0].get("ocr", False) == line.get("ocr", False):
            groups[-1].append(line)
        else:
            groups.append([line])
    for group in groups:
        for text in _paragraphs(group, gap):
            blocks.append(Block(seq=len(blocks), kind="P", text=text, line_no=_next_line(blocks),
                                line_count=text.count("\n") + 1,
                                ocr=group[0].get("ocr", False)))


OCR_DPI = 300


def _ocr_page(page) -> list[dict]:
    """글자 층이 없는 쪽을 그림으로 만들어 OCR한 줄 (add-ocr). 위치는 쪽 좌표로 바꾼다."""
    if not ocr.available():
        return []
    image = page.to_image(resolution=OCR_DPI).original
    scale = page.height / image.height
    return [{"text": ln.text, "top": ln.top * scale, "bottom": ln.bottom * scale,
             "x0": 0, "x1": page.width, "ocr": True} for ln in ocr.read_lines(image)]


def _ocr_region(page, bbox: tuple) -> list[dict]:
    """글자 쪽에 박은 그림 영역을 OCR한 줄 (update-pdf-drawings). 위치는 쪽 좌표로 바꾼다."""
    if not ocr.available():
        return []
    image = page.crop(bbox).to_image(resolution=OCR_DPI).original
    scale = (bbox[3] - bbox[1]) / image.height
    top = bbox[1]
    return [{"text": ln.text, "top": top + ln.top * scale, "bottom": top + ln.bottom * scale,
             "x0": 0, "x1": page.width, "ocr": True} for ln in ocr.read_lines(image)]


def _page_figures(page) -> list[tuple]:
    """글자 쪽의 큰 그림 위치 (x0, top, x1, bottom). 쪽 밖으로 나간 부분은 자른다."""
    out = []
    for im in page.images:
        box = (max(im["x0"], 0), max(im["top"], 0), min(im["x1"], page.width),
               min(im["bottom"], page.height))
        w, h = box[2] - box[0], box[3] - box[1]
        if w >= FIGURE_MIN and h >= FIGURE_MIN and w * h >= page.width * page.height * FIGURE_AREA:
            out.append(box)
    return out


def _text_inside(page, box: tuple) -> int:
    """그림 영역 안(글자 가운데 점 기준)의 글자층 글자 수 (빈칸 뺌)"""
    x0, top, x1, bottom = box
    return sum(1 for ch in page.chars if ch["text"].strip()
               and x0 <= (ch["x0"] + ch["x1"]) / 2 <= x1
               and top <= (ch["top"] + ch["bottom"]) / 2 <= bottom)


def _drawing_caption(tables, lines: list[dict]) -> str:
    """도면 쪽 그림 설명 "도면 <번호> · <제목>". 표제란 칸에서, 없으면 글자 줄에서 찾는다."""
    number = title = None
    for t in tables:
        for row in t.extract():
            cells = [(c or "").strip() for c in row]
            if len(cells) >= 2 and cells[1]:
                if DRAWING_NO.match(cells[0]):
                    number = number or cells[1]
                elif TITLE.match(cells[0]):
                    title = title or cells[1]
    if number is None:
        for ln in lines:
            if _label(ln["text"]) and (m := NUMBER.search(ln["text"])):
                number = m.group(1)
                break
    return " · ".join(["도면" + (f" {number}" if number else "")] + ([title] if title else []))


def _add_figure(blocks: list[Block], caption: str | None, ocr_lines: list[dict]) -> None:
    """그림 블록(빈 글자, 그림 위치 기록)과 그림 속 OCR 단락."""
    blocks.append(Block(seq=len(blocks), kind="P", text="", line_no=_next_line(blocks),
                        line_count=1, has_figure=True, caption=caption))
    _add_paragraphs(blocks, ocr_lines)


def _add_table(blocks: list[Block], rows: list[list[str | None]], table_no: int) -> None:
    for row_no, row in enumerate(rows):
        cells = [(c or "").strip() for c in row]
        if not any(cells):
            continue
        text = " | ".join(cells)
        blocks.append(Block(seq=len(blocks), kind="R", text=text, line_no=_next_line(blocks),
                            line_count=text.count("\n") + 1, table_no=table_no, row_no=row_no,
                            cells=cells, raw_cells=list(cells)))


MARK_ONLY = re.compile(r"^([CDE])$")                    # 조항 줄 위에 따로 놓인 준수 표시
MARK_LEAD = re.compile(r"^([CDE])\s+(\S.*)$")             # 표시가 조항 줄 앞에 붙음 ("C 1. …")
LEGEND_BLOCKS = 60                                        # 앞 몇 단락에서 준수 표시 머리를 찾나


def _section_heading(text: str) -> bool:
    """답안 표 밖에 두는 절 제목: 장·PART, "1.1"처럼 점이 든 번호. "A."·"1." 조항은 표 행이다."""
    h = heading_of(text)
    if h is None:
        return False
    style = h[0]                         # NUM 뒤 숫자는 번호 안 점 수 ("1.1" → NUM1, "1." → NUM0)
    return style in ("CHAPTER", "PART") or (style.startswith("NUM") and style != "NUM0")


def _mark_rows(blocks: list[Block]) -> list[Block]:
    """공급사 답안 PDF: 선 없는 표의 조항을 표 행으로 되돌린다 (update-pdf-tables).

    준수 표시 머리가 있는 문서에서만, 머리 뒤 단락 중 제목이 아닌 조항을 [표시, 조항] 행으로 만든다.
    조항 위에 따로 놓인 C/D/E 단락은 바로 다음 조항의 표시로 붙인다. docx는 같은 조항이 표 행이라
    공급사 답안 규칙(MARK_TABLE_ROWS)이 같게 걸린다.
    """
    start = next((i for i, b in enumerate(blocks[:LEGEND_BLOCKS])
                  if b.kind == "P" and MARK_LEGEND.search(b.text)), None)
    if start is None:
        return blocks
    table_no = max((b.table_no for b in blocks if b.table_no is not None), default=-1) + 1
    out = blocks[:start + 1]
    i, row_no = start + 1, 0
    while i < len(blocks):
        b = blocks[i]
        mark, text, lines = "", b.text, b.line_count
        if b.kind != "P" or b.has_figure or _section_heading(b.text):
            out.append(b)
            i += 1
            continue
        if (m := MARK_ONLY.match(b.text.strip())) and i + 1 < len(blocks) \
                and blocks[i + 1].kind == "P" and not _section_heading(blocks[i + 1].text):
            mark, text = m.group(1), blocks[i + 1].text
            lines += blocks[i + 1].line_count
            i += 1
        elif m := MARK_LEAD.match(b.text.strip()):
            mark, text = m.group(1), m.group(2)
        cells = [mark, text]
        out.append(Block(seq=0, kind="R", text=" | ".join(cells), line_no=b.line_no,
                         line_count=lines, table_no=table_no, row_no=row_no, cells=cells,
                         raw_cells=list(cells), page=b.page))
        row_no += 1
        i += 1
    for n, b in enumerate(out):
        b.seq = n
    return out


def read_blocks(path: Path) -> list[Block]:
    try:
        pdf = pdfplumber.open(str(path))
    except Exception:                                   # 암호·깨진 PDF: 판독 불가
        return []
    with pdf:
        pages = []
        for page in pdf.pages:
            # 돌아간 글자는 줄로 읽지 않는다 (update-pdf-drawings)
            rotated = sum(1 for ch in page.chars if not _straight(ch) and ch["text"].strip())
            flat = page.filter(_straight) if rotated else page
            tables = flat.find_tables()
            lines = [ln for ln in flat.extract_text_lines() if ln["text"].strip()]
            figures: list[tuple] = []                   # (위치, 설명, 그림 속 OCR 줄)
            if not lines and not tables:
                lines = _ocr_page(page)                 # 스캔한 쪽 (add-ocr)
            elif _drawing_page(tables, lines):
                # 도면 쪽: 라벨·치수·표제란은 읽지 않고 주기 줄만 한 줄씩
                figures.append((0, _drawing_caption(tables, lines), []))
                lines = [{**ln, "own": True} for ln in lines if NOTE.match(ln["text"])]
                tables = []
            else:
                # 글자층이 깔린 그림은 이미 읽은 글자라 OCR하지 않는다 (위치만 남김)
                figures += [(box[1], None, [] if _text_inside(flat, box) >= FIGURE_TEXT_CHARS
                             else _ocr_region(page, box)) for box in _page_figures(page)]
            if rotated:
                figures.append((page.height, f"돌아간 글자 {rotated}자", []))
            boxes = [t.bbox for t in tables]
            pages.append((page, tables, [ln for ln in lines if not _inside(ln, boxes)], figures))
        # 쪽 절반 이상(2쪽 이상)에서 같은 높이에 반복되는 줄은 머리말·꼬리말
        counts = Counter(k for page, _, lines, _ in pages
                         for k in {_edge_key(ln, page.height) for ln in lines} if k)
        repeated = {k for k, n in counts.items() if len(pages) >= 2 and n >= max(2, len(pages) / 2)}

        blocks: list[Block] = []
        table_no = -1
        for page_no, (page, tables, lines, figures) in enumerate(pages, start=1):
            first = len(blocks)
            items = [(ln["top"], "P", ln) for ln in lines
                     if _edge_key(ln, page.height) not in repeated]
            items += [(t.bbox[1], "T", t) for t in tables]
            items += [(top, "F", (caption, found)) for top, caption, found in figures]
            items.sort(key=lambda it: (it[0], it[1]))   # 같은 높이면 그림 → 단락 → 표
            gap = line_gap([obj for _, kind, obj in items if kind == "P"])
            # 위에서 아래로: 표 사이의 글자 줄은 모아 두었다가 단락으로 묶는다
            pending: list[dict] = []
            for _, kind, obj in items:
                if kind == "P":
                    pending.append(obj)
                    continue
                _add_paragraphs(blocks, pending, gap)
                pending = []
                if kind == "F":
                    _add_figure(blocks, *obj)
                    continue
                table_no += 1
                _add_table(blocks, obj.extract(), table_no)
            _add_paragraphs(blocks, pending, gap)
            for b in blocks[first:]:
                b.page = page_no
    return _mark_rows(blocks)


def page_starts(blocks: list[Block]) -> list[int] | None:
    """쪽마다 첫 줄 번호 (add-pdf-page-location). 블록 없는 쪽은 다음 쪽 첫 줄과 같다.

    줄 번호 → 쪽은 시작 줄이 그 줄 이하인 가장 큰 쪽 (DB 함수 line_page, page_of).
    """
    pages = [b.page for b in blocks if b.page]
    if not pages:
        return None
    first = {}
    for b in blocks:
        if b.page and b.page not in first:
            first[b.page] = b.line_no
    out, nxt = [], blocks[-1].last_line + 1
    for p in range(max(pages), 0, -1):
        nxt = first.get(p, nxt)
        out.append(nxt)
    return out[::-1]


def page_of(starts: list[int] | None, line: int | None) -> int | None:
    """줄 번호가 있는 쪽 (DB 함수 line_page와 같은 규칙)"""
    if not starts or line is None:
        return None
    return max((n for n, s in enumerate(starts, start=1) if s <= line), default=None)
