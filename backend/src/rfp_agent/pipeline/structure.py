"""FR-02 구조 나누기. 코드만 쓴다.

- 절: 제목 스타일이 없어서 번호 모양("PART 1", "1.1", "A.", "가.", "1)", "가)")으로 복원한다.
  번호 모양이 처음 나오면 한 단계 아래, 이미 나온 모양이면 그 단계로 돌아간다.
- 표: 칸 이름 사전으로 머리글 행과 칸 역할을 찾고, 쪽 넘김으로 나뉜 Word 표를 하나로 잇는다.
"""

import re
from bisect import bisect_right
from dataclasses import dataclass, field

from rfp_agent.pipeline.docx_reader import Block

HEADING_MAX_LEN = 100
TOC_LEADER = re.compile(r"\.{5,}\s*\d+\s*$")
TOC_CLUSTER = 3

NUMBERING = [
    ("PART", re.compile(r"^PART\s+(\d+)\b\s*[-–.]?\s*(.*)$", re.IGNORECASE)),
    ("CHAPTER", re.compile(r"^(제\s*\d+\s*[장편절])\s*(.*)$")),
    # "4. 제목", "3.4.10 제목". "1)"은 PAREN_NUM이다.
    ("NUM", re.compile(r"^(\d+(?:\.\d+)+\.?|\d+\.)\s*([^\s)].*)$")),
    ("ALPHA", re.compile(r"^([A-Z])\.\s*(\S.*)$")),
    # [가-하]는 "표", "그" 같은 글자까지 포함하므로 순서 글자만 쓴다.
    ("HANGUL", re.compile(r"^([가나다라마바사아자차카타파하])\.\s*(\S.*)$")),
    ("PAREN_NUM", re.compile(r"^(\d+)\)\s*(\S.*)$")),
    ("PAREN_HANGUL", re.compile(r"^([가나다라마바사아자차카타파하])\)\s*(\S.*)$")),
    ("PAREN2_NUM", re.compile(r"^\((\d+)\)\s*(\S.*)$")),
]
ROLE_ITEM_NO, ROLE_NAME, ROLE_UNIT = "ITEM_NO", "ITEM_NAME", "UNIT"
ROLE_REQUIRED, ROLE_WARRANTED, ROLE_MARK = "REQUIRED", "WARRANTED", "SUPPLIER_MARK"
TABLE_NAME = re.compile(r"\b(TS-[A-Z0-9][A-Z0-9-]*[A-Z0-9])\b")
SUB_ITEM = re.compile(r"^\s*[-–•]\s*")


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("’", "'").replace("‘", "'")).strip()


# ---------------------------------------------------------------- 절

@dataclass
class Section:
    index: int
    block_seq: int
    line_start: int
    style: str
    number: str
    title: str
    level: int
    parent: int | None
    is_toc: bool = False
    structure_flag: bool = False
    line_end: int | None = None
    line_offset: int = 0        # 단락 안 몇 번째 줄에서 시작하는지 (줄바꿈 뒤 제목)


# 공급사 답안의 준수 표시 머리 ("C: Complied D: Deviation E: Exclusion"). PDF는 옆 칸 글자가
# 사이에 끼어 "C: ELECTRIC DISTRIBUTION Complied"로 읽히기도 해 낱말 몇 개는 건너뛴다
# (update-pdf-tables)
MARK_LEGEND = re.compile(r"\bC:\s*(?:\S+\s+){0,4}?Complied")


def heading_of(text: str) -> tuple[str, str, str] | None:
    """번호가 붙은 짧은 단락(또는 단락 첫 줄)이면 (모양, 번호, 제목).

    "6. CLARIFICATION ...⏎본문"처럼 제목 뒤에 줄바꿈으로 본문이 붙은 단락도 첫 줄을 제목으로 본다.
    """
    line = normalize(text.strip().split("\n")[0])
    if not line or len(line) > HEADING_MAX_LEN:
        return None
    for style, pattern in NUMBERING:
        m = pattern.match(line)
        if not m:
            continue
        number, title = m.group(1).rstrip("."), TOC_LEADER.sub("", m.group(2)).strip()
        if not title or title.endswith((".", "다.")) and not TOC_LEADER.search(line) \
                or re.search(r"다\.\s", title):
            # 문장으로 끝나면 번호 매긴 본문이지 제목이 아니다.
            return None
        if style == "NUM":
            style = f"NUM{number.count('.')}"
            if re.fullmatch(r"[\d.,\s%]+", title):
                return None
        return style, number, title
    return None


def _number_value(style: str, number: str) -> int | None:
    last = number.split(".")[-1] if style.startswith("NUM") else number
    if last.isdigit():
        return int(last)
    if len(last) == 1 and "A" <= last <= "Z":
        return ord(last) - ord("A") + 1
    if len(last) == 1 and "가" <= last <= "하":
        return "가나다라마바사아자차카타파하".find(last) + 1 or None
    return None


def find_sections(blocks: list[Block]) -> list[Section]:
    candidates: list[tuple[Block, int, tuple[str, str, str]]] = []
    for b in blocks:
        if b.kind != "P":
            continue
        # 단락 첫 줄, 그리고 줄바꿈(w:br) 뒤에 붙은 제목 ("…한다.)⏎바.구조 일반⏎본문")
        for offset, line in enumerate(b.text.strip().split("\n")):
            if h := heading_of(line):
                candidates.append((b, offset, h))

    # 목차: 연달아 나온 제목 묶음(사이에 본문 없음)에서
    # 3개 이상 또는 절반 이상이 뒤에 다시 나오면 목차.
    # ("가. 일반사항"처럼 장마다 되풀이되는 제목 하나만으로는 목차로 보지 않는다.)
    toc_seqs: set[int] = set()
    key_of = {b.seq: normalize(f"{number} {title}").lower()
              for b, offset, (_, number, title) in candidates if offset == 0}
    last_seq_of: dict[str, int] = {}
    for seq, key in key_of.items():
        last_seq_of[key] = seq
    run: list[int] = []
    for b in [b for b in blocks if b.kind == "P" and b.text.strip()] + [None]:
        if b is not None and b.seq in key_of:
            run.append(b.seq)
            continue
        if len(run) >= TOC_CLUSTER:
            repeated = [s for s in run if last_seq_of[key_of[s]] > s]
            if len(repeated) >= TOC_CLUSTER or len(repeated) * 2 >= len(run):
                toc_seqs.update(repeated)
        run = []
    for b, offset, _ in candidates:
        if offset == 0 and TOC_LEADER.search(b.text):
            toc_seqs.add(b.seq)

    sections: list[Section] = []
    stack: list[tuple[str, int]] = []           # (모양, 절 index)
    last_value: dict[int, int] = {}             # 부모 절 index → 같은 모양 마지막 번호
    for b, offset, (style, number, title) in candidates:
        is_toc = offset == 0 and b.seq in toc_seqs
        if is_toc:
            sections.append(Section(len(sections), b.seq, b.line_no, style, number, title,
                                    level=0, parent=None, is_toc=True))
            continue
        styles = [s for s, _ in stack]
        if style in styles:
            del stack[styles.index(style):]
        parent = stack[-1][1] if stack else None
        index = len(sections)
        value = _number_value(style, number)
        key = parent if parent is not None else -1
        flag = False
        if value is not None:
            prev = last_value.get((key, style))
            flag = prev is not None and value not in (prev + 1, prev)
            last_value[(key, style)] = value
        sections.append(Section(index, b.seq, (b.line_no or 0) + offset, style, number, title,
                                level=len(stack) + 1, parent=parent, structure_flag=flag,
                                line_offset=offset))
        stack.append((style, index))

    body = [s for s in sections if not s.is_toc]
    last_line = blocks[-1].last_line if blocks else 0
    for cur, nxt in zip(body, body[1:] + [None], strict=False):
        cur.line_end = (nxt.line_start - 1) if nxt else last_line
    return sections


class SectionIndex:
    """블록 순서로 그 블록이 속한 가장 안쪽 절(목차 제외)을 찾는다.

    단락 중간 줄에서 시작한 절은 그 단락이 아니라 다음 블록부터 적용한다.
    """

    def __init__(self, sections: list[Section]):
        self.sections = sections
        self._body = [s for s in sections if not s.is_toc]
        self._keys = [(s.block_seq, s.line_offset) for s in self._body]

    def at(self, block_seq: int) -> Section | None:
        i = bisect_right(self._keys, (block_seq, 0))
        return self._body[i - 1] if i else None


def ancestors(sections: list[Section], section: Section | None) -> list[Section]:
    out = []
    while section is not None:
        out.append(section)
        section = sections[section.parent] if section.parent is not None else None
    return out


# ---------------------------------------------------------------- 표

@dataclass
class TableRow:
    block: Block
    item_no: str | None
    item_name: str | None
    unit: str | None
    required: str | None
    warranted: str | None
    supplier_mark: str | None
    parent_index: int | None = None     # 같은 표 rows 안의 상위 항목 위치


@dataclass
class LogicalTable:
    name: str | None
    source_table_nos: list[int]
    column_roles: dict[int, str]
    header_signature: str | None
    title_rows: list[str]
    rows: list[TableRow] = field(default_factory=list)
    role_flag: bool = False
    first_block_seq: int = 0
    instance: int = 1               # 같은 이름 표가 문서에 여러 번 나오면 몇 번째인지 (설비가 다름)

    @property
    def is_datasheet(self) -> bool:
        return ROLE_REQUIRED in self.column_roles.values()


def column_roles_of(cells: list[str], role_dict: dict[str, str]) -> dict[int, str]:
    roles = {}
    lowered = {normalize(k).lower(): v for k, v in role_dict.items()}
    for i, cell in enumerate(cells):
        role = lowered.get(normalize(cell).lower())
        if role:
            roles[i] = role
    return roles


def _cell(raw: list[str], roles: dict[int, str], role: str) -> str | None:
    texts = []
    for i, r in roles.items():
        if r == role and i < len(raw):
            t = raw[i].strip()
            if t and t not in texts:
                texts.append(t)
    return " ".join(texts) if texts else None


def _supplier_mark(raw: list[str]) -> str | None:
    marks = [c.strip() for c in raw if c.strip() in ("C", "D", "E")]
    return marks[-1] if marks else None


MAX_ITEM_NO = 20
CAPTION_MAX_LEN = 150           # 표 앞 단락을 표 제목으로 볼 최대 길이


def _item_number(item_no: str | None) -> int | None:
    if item_no and (m := re.match(r"^(\d+)", item_no.strip())):
        return int(m.group(1))
    return None


def build_tables(blocks: list[Block], role_dict: dict[str, str],
                 supplier_marks: bool = False) -> list[LogicalTable]:
    by_table: dict[int, list[Block]] = {}
    between_text: dict[int, bool] = {}       # 이 표 앞에 내용 있는 단락이 있었나
    caption: dict[int, str] = {}             # 표 바로 앞 단락 (표 제목 줄이 표 밖에 있을 때)
    seen_text = False
    last_text: str | None = None
    for b in blocks:
        if b.kind == "R":
            if b.table_no not in by_table:
                between_text[b.table_no] = seen_text
                if seen_text and last_text is not None:
                    caption[b.table_no] = last_text
                by_table[b.table_no] = []
                seen_text = False
            by_table[b.table_no].append(b)
            last_text = None
        elif b.text.strip():
            seen_text = True
            last_text = normalize(b.text)

    tables: list[LogicalTable] = []
    for table_no, rows in by_table.items():
        header_at = next((i for i, r in enumerate(rows)
                          if len(set(column_roles_of(r.raw_cells, role_dict).values())) >= 2), None)
        if header_at is None:
            roles, signature, titles, data = {}, None, [], rows
        else:
            roles = column_roles_of(rows[header_at].raw_cells, role_dict)
            signature = normalize(rows[header_at].text)
            titles = [normalize(r.text) for r in rows[:header_at]]
            data = rows[header_at + 1:]
        name = next((m.group(1) for t in titles if (m := TABLE_NAME.search(t))), None)
        if name is None and header_at is not None and (cap := caption.get(table_no)) \
                and len(cap) <= CAPTION_MAX_LEN and (m := TABLE_NAME.match(cap)):
            # 표 안에 제목 줄이 없고 바로 앞 단락이 "TS-170-GIS — …"처럼 표 이름으로 시작하면
            # 그 단락을 표 제목으로 본다. 본문 속 "Refer to TS-…" 같은 언급은 쓰지 않는다.
            name = m.group(1)

        prev = tables[-1] if tables else None
        continues = (
            prev is not None and header_at is not None and name is not None
            and prev.name == name and prev.header_signature == signature
            and not between_text[table_no]
        )
        if continues:
            last_no = next((n for r in reversed(prev.rows) if (n := _item_number(r.item_no))), None)
            first_no = next((n for r in data
                             if (n := _item_number(_cell(r.raw_cells, roles, ROLE_ITEM_NO)))), None)
            continues = last_no is None or first_no is None or first_no in (last_no, last_no + 1)
        if continues:
            table = prev
            table.source_table_nos.append(table_no)
        else:
            table = LogicalTable(name=name, source_table_nos=[table_no], column_roles=roles,
                                 header_signature=signature, title_rows=titles,
                                 role_flag=header_at is None, first_block_seq=rows[0].seq)
            tables.append(table)

        repeated = set(table.title_rows) | ({signature} if signature else set())
        for r in data:
            if normalize(r.text) in repeated:
                continue            # 쪽마다 반복되는 머리글
            if not any(c.strip() for c in r.raw_cells):
                continue
            mark = _supplier_mark(r.raw_cells) if supplier_marks else None
            item_no = _cell(r.raw_cells, roles, ROLE_ITEM_NO)
            item_name = _cell(r.raw_cells, roles, ROLE_NAME)
            if item_no and len(item_no) > MAX_ITEM_NO:
                # 병합 칸("TOTAL Column 6 ...")은 번호가 아니라 이름으로 본다.
                item_name, item_no = item_name or item_no, None
            table.rows.append(TableRow(
                block=r,
                item_no=item_no,
                item_name=item_name,
                unit=_cell(r.raw_cells, roles, ROLE_UNIT),
                required=_cell(r.raw_cells, roles, ROLE_REQUIRED),
                warranted=_cell(r.raw_cells, roles, ROLE_WARRANTED),
                supplier_mark=mark or _cell(r.raw_cells, roles, ROLE_MARK),
            ))
    seen: dict[str, int] = {}
    for table in tables:
        link_sub_items(table)
        if table.name:
            seen[table.name] = table.instance = seen.get(table.name, 0) + 1
    return tables


def link_sub_items(table: LogicalTable) -> None:
    """번호 없는 "- …" 행을 바로 위 번호 항목의 하위로 잇고 "20-1"처럼 번호를 붙인다."""
    parent, count = None, 0
    for i, row in enumerate(table.rows):
        if row.item_no and _item_number(row.item_no) is not None:
            parent, count = i, 0
            continue
        if not row.item_no and parent is not None and row.item_name \
                and SUB_ITEM.match(row.item_name):
            count += 1
            row.parent_index = parent
            row.item_no = f"{table.rows[parent].item_no.strip()}-{count}"
        elif row.item_no:
            parent = None
