"""FR-05 값 정리. 코드만 쓰고 단위는 환산하지 않는다 (CR-10)."""

import ast
import math
import operator as op
import re
from dataclasses import dataclass, field

from rfp_agent.pipeline.docx_reader import is_redacted
from rfp_agent.pipeline.extract import STANDARD_TITLE, Candidate
from rfp_agent.pipeline.structure import Section, ancestors, normalize

YESNO = {"required", "yes", "no", "not required", "필요", "불필요", "요", "부"}
EMPTY_MARKS = {"", "-", "–", "—", "n/a", "na"}
DELEGATED = re.compile(r"^(as per|according to|in accordance with|refer to|acc\. to|per)\b",
                       re.IGNORECASE)
STANDARD_REF = re.compile(
    r"\b(IEC|IEEE|ANSI|NEMA|UL|KS\s?[A-Z]|ES)\s?[:\-]?\s?([0-9][0-9A-Za-z.\-]*[0-9A-Za-z])")
FORMULA_CHARS = re.compile(r"[×√*]|\d\s*[xX]\s*\d")
SIMPLE_NUMBER = re.compile(r"^(<=|>=|≤|≥|<|>|=)?\s*(-?\d[\d,]*(?:\.\d+)?)\s*([^\d\s].*)?$")
OPERATORS = {"≤": "<=", "≥": ">=", "<=": "<=", ">=": ">=", "<": "<", ">": ">", "=": "="}
KOREAN_BOUNDS = {"이내": "<=", "이하": "<=", "미만": "<", "이상": ">=", "초과": ">"}
TIME_CONDITION = re.compile(r"\(\s*(\d+(?:\.\d+)?)\s*(?:sec(?:onds?)?|s|초)\.?\s*\)", re.IGNORECASE)
UNITS = (r"kVA|MVA|kVAr|kV|kA|kW|MW|A|V|Hz|%|°C|℃|deg\.? ?C|°F|deg\.? ?F|oC|pC|dB|mm|m|ft|"
         r"sec|ms|cycles?|kg|bar|MPa|months?|years?|초|분|년")
_BOUNDS = "|".join(KOREAN_BOUNDS)
SENTENCE_VALUE = re.compile(
    rf"(<=|>=|≤|≥|<|>)?\s*(\d[\d,]*(?:\.\d+)?)\s*({UNITS})(?![A-Za-z])(\s*(?:{_BOUNDS}))?"
)
SITE = re.compile(r"(\d+\s*kV\s*변전소|[가-힣]+전기실)")
QUALIFIER = re.compile(r"^\s*\(([^)]{1,30})\)")
UNIT_ITEM_FALLBACK = {"kva": "rated_capacity", "mva": "rated_capacity"}
# 항목마다 맞는 단위. 문장 속 값의 단위가 안 맞으면 그 항목 값으로 보지 않는다
# ("정격전류의 25 %"는 정격 전류 값이 아니고, "nominal voltage … 50 Hz"는 전압이 아니다).
_V, _A = r"k?V(?:rms|p|peak)?", r"k?A(?:rms|p|peak)?"   # "kVrms", "kVp"도 전압
ITEM_UNITS = {
    "rated_voltage_um": _V, "nominal_voltage": _V, "lightning_impulse": _V,
    "power_freq_withstand": _V, "switching_impulse": _V, "control_voltage": _V,
    "rated_current": _A, "short_time_current": _A, "breaking_current": _A,
    "peak_current": _A, "making_current": _A,
    "rated_frequency": r"Hz", "gas_leakage_rate": r"%", "partial_discharge": r"pC",
    "breaking_time": r"ms|cycles?", "closing_time": r"ms|cycles?",
    "ambient_temp_max": r"°C|℃|deg\.? ?[CF]|°F|oC", "altitude": r"m|ft",
    "rated_capacity": r"kVA|MVA|kW|MW|Ah", "weight": r"kg|t|ton",
    "sound_level": r"dB(?:\s*\(A\))?",
}
TEXT_ITEMS = {"manufacturer", "country_of_origin", "model_number", "standard",
              "operating_sequence"}     # 숫자 값이 아닌 항목
RANGE = re.compile(r"(\d[\d,.]*)\s*(?:[A-Za-z%°℃]+)?\s*(?:~|∼|～|\bto\b)\s*(\d[\d,.]*)"
                   r"|between\s+(?:the\s+limits\s+of\s+)?(\d[\d,.]*)\s*(?:[A-Za-z%°℃]+)?\s+and\s+"
                   r"(\d[\d,.]*)", re.IGNORECASE)


def unit_fits(item_key: str | None, unit: str | None) -> bool:
    if item_key is None or not unit:
        return True
    if item_key in TEXT_ITEMS:
        return False
    pattern = ITEM_UNITS.get(item_key)
    return pattern is None or re.fullmatch(pattern, unit.strip(), re.IGNORECASE) is not None
# 한 단락 안의 문장 경계 ("…한다. 또 …", "… shall be. The …", ";")
CLAUSE_END = re.compile(r"(?<=다\.)\s+|(?<=\.)\s+(?=[A-Z])|;\s*")


@dataclass
class Value:
    raw_text: str | None
    cell_form: str
    num_value: float | None = None
    operator: str | None = None
    unit_raw: str | None = None
    cond_time_s: float | None = None
    cond_raw: str | None = None
    item_key: str | None = None
    target_object: str | None = None
    basis_standard: str | None = None
    delegated_std: str | None = None
    equipment_key: str | None = None
    flag: str | None = None
    seq: int = 1
    pos: int = 0                # 문장 속 위치 (저장하지 않음)


@dataclass
class Dictionaries:
    aliases: list[tuple[str, str]]              # (원문 표현 소문자, 항목키) 긴 것 먼저
    targets: list[tuple[str, str, str | None]]  # (표현 소문자, 대상, 상위 대상) 긴 것 먼저
    parents: dict[str, str] = field(default_factory=dict)  # 대상 → 상위 대상

    @classmethod
    def build(cls, aliases: dict[str, str], targets: list[tuple[str, str, str | None]]):
        a = sorted(((normalize(k).lower(), v) for k, v in aliases.items()),
                   key=lambda x: -len(x[0]))
        t = sorted(((normalize(k).lower(), v, p) for k, v, p in targets),
                   key=lambda x: -len(x[0]))
        return cls(a, t, {v: p for _, v, p in targets if p})


# ---------------------------------------------------------------- 계산식

_ALLOWED = {ast.Mult: op.mul, ast.Div: op.truediv, ast.Add: op.add, ast.Sub: op.sub}


def evaluate_formula(text: str) -> float | None:
    """×, /, √, 괄호(와 + -)만 쓴 계산식을 계산한다. 그 밖이면 None."""
    expr = text.replace(",", "").replace("×", "*").replace("÷", "/")
    expr = re.sub(r"(?<=[\d)\s])[xX](?=[\s\d(√])", "*", expr)
    expr = re.sub(r"√\s*(\d+(?:\.\d+)?|\([^()]*\))", r"sqrt(\1)", expr)
    if not re.fullmatch(r"[\d.\s*/()+\-sqrt]+", expr):
        return None

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED:
            return _ALLOWED[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -ev(node.operand)
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "sqrt" and len(node.args) == 1):
            return math.sqrt(ev(node.args[0]))
        raise ValueError("허용하지 않는 계산식")

    try:
        return ev(ast.parse(expr, mode="eval"))
    except (ValueError, SyntaxError, ZeroDivisionError):
        return None


# ---------------------------------------------------------------- 공통

def number(text: str) -> float:
    return float(text.replace(",", ""))


def standard_of(text: str | None) -> str | None:
    if not text:
        return None
    m = STANDARD_REF.search(text)
    return f"{re.sub(r'\s+', ' ', m.group(1))} {m.group(2)}" if m else None


LIST_MARK = re.compile(r"^(?:[-–•·]\s*|\(?\d+\)\s*|\(?[a-z]\)\s+)+")


def item_key_of(name: str | None, dicts: Dictionaries, contains: bool = False) -> str | None:
    if not name:
        return None
    # "- Short-duration …", "2) Short circuit …"의 목록 표시는 항목 이름이 아니다.
    text = LIST_MARK.sub("", normalize(name).lower())
    for alias, key in dicts.aliases:
        if text.startswith(alias) or (contains and alias in text):
            return key
    return None


def target_of(text: str | None, dicts: Dictionaries) -> str | None:
    if not text:
        return None
    low = normalize(text).lower()
    for term, target, _ in dicts.targets:
        if re.search(rf"(?<![a-z]){re.escape(term)}(?![a-z])", low):
            return target
    return None


def context_target(c: Candidate, sections: list[Section], dicts: Dictionaries,
                   doc_target: str | None) -> str | None:
    """문장·행 자체 → 표 구분 행 → 표 이름 → 절 제목 → 문서 제목 순서로 찾는다.

    절 제목은 속한 절부터 위로 올라가며, 단계마다 같은 단계의 앞 절도 본다.
    ("나. 차단기" 다음의 "바. 구조 일반"은 다음 설비 "사. 단로기" 전까지 차단기 이야기다.)
    """
    for text in (c.text, c.part_title, c.table.name if c.table else None):
        if t := target_of(text, dicts):
            return t
    for s in ancestors(sections, c.section) if c.section is not None else []:
        for sibling in [s, *preceding_siblings(sections, s)]:
            if t := target_of(sibling.title, dicts):
                return t
    return doc_target


def table_label(table) -> str:
    if not table.name:
        return f"표 {table.source_table_nos[0]}"
    return table.name if table.instance == 1 else f"{table.name} #{table.instance}"


def preceding_siblings(sections: list[Section], section: Section):
    """같은 상위 절 아래에서 앞에 나온 절들 (가까운 것부터)."""
    for s in reversed(sections[:section.index]):
        if s.index == section.parent:
            return
        if s.parent == section.parent and not s.is_toc:
            yield s


# ---------------------------------------------------------------- 표 칸

def cell_values(raw: str | None, unit: str | None) -> list[Value]:
    text = normalize(raw or "")
    # "25 (2seconds)"처럼 값 뒤 괄호의 시간은 조건이다.
    time = TIME_CONDITION.search(text)
    if time and SIMPLE_NUMBER.match(text[:time.start()].strip()):
        values = cell_values(text[:time.start()].strip(), unit)
        for v in values:
            v.raw_text, v.cond_time_s = raw, float(time.group(1))
        return values
    if is_redacted(text):
        return [Value(raw_text=raw, cell_form="EMPTY", flag="REDACTED")]    # CR-05 값 없음
    if text.lower() in EMPTY_MARKS:
        return [Value(raw_text=raw, cell_form="EMPTY", unit_raw=unit)]
    if text.lower() in YESNO:
        return [Value(raw_text=raw, cell_form="YESNO", unit_raw=unit)]
    if DELEGATED.match(text):
        return [Value(raw_text=raw, cell_form="DELEGATED", unit_raw=unit,
                      delegated_std=standard_of(text))]
    if FORMULA_CHARS.search(text):
        result = evaluate_formula(text)
        return [Value(raw_text=raw, cell_form="FORMULA", num_value=result, unit_raw=unit,
                      flag=None if result is not None else "FORMULA_NOT_ALLOWED")]
    parts = [p.strip() for p in re.split(r"\s*/\s*", text)] if "/" in text else [text]
    values = []
    for i, part in enumerate(parts, start=1):
        m = SIMPLE_NUMBER.match(part)
        if not m or (m.group(3) and not re.fullmatch(rf"\s*({UNITS})\s*", m.group(3))):
            return [Value(raw_text=raw, cell_form="TEXT", unit_raw=unit)]
        values.append(Value(
            raw_text=raw, cell_form="NUMBER", num_value=number(m.group(2)),
            operator=OPERATORS.get(m.group(1) or "=", "="),
            unit_raw=unit or (m.group(3).strip() if m.group(3) else None), seq=i,
        ))
    for v in values:
        if not v.unit_raw:
            v.flag = "UNIT_MISSING"
    return values


# ---------------------------------------------------------------- 문장

def sentence_values(text: str) -> list[Value]:
    # "154kV 변전소" 같은 장소 이름 속 숫자는 값이 아니다.
    site_spans = [m.span() for m in SITE.finditer(text)]
    # "47 ~ 52 Hz" 같은 범위의 양 끝은 하한·상한이다.
    if STANDARD_TITLE.search(text):
        return []
    range_starts: dict[int, str] = {}
    for m in RANGE.finditer(text):
        lo, hi = (1, 2) if m.group(1) else (3, 4)
        range_starts[m.start(lo)], range_starts[m.start(hi)] = ">=", "<="
    values = []
    for m in SENTENCE_VALUE.finditer(text):
        if any(a <= m.start(2) < b for a, b in site_spans):
            continue
        sym, num, unit, bound = m.group(1), m.group(2), m.group(3), (m.group(4) or "").strip()
        operator = OPERATORS.get(sym) if sym else KOREAN_BOUNDS.get(bound, "=")
        qualifier = QUALIFIER.match(text[m.end():])
        # 값 바로 뒤 괄호는 조건이다. 괄호 안이 또 값이면 ("104 deg F (40 deg C)") 조건이 아니다.
        is_value = qualifier and SENTENCE_VALUE.fullmatch(qualifier.group(1).strip())
        cond = qualifier.group(1) if qualifier and not is_value else None
        values.append(Value(
            raw_text=m.group(0).strip(), cell_form="NUMBER", num_value=number(num),
            operator=range_starts.get(m.start(2), operator), unit_raw=unit, cond_raw=cond,
            seq=len(values) + 1, pos=m.start(2),
            flag="RANGE" if m.start(2) in range_starts else None,
        ))
    return values


def clause_at(text: str, pos: int) -> str:
    """pos가 들어 있는 문장 하나."""
    start = 0
    for m in CLAUSE_END.finditer(text):
        if m.start() >= pos:
            return text[start:m.start()]
        start = m.end()
    return text[start:]


def site_of(value: Value, text: str, preceding: str) -> str | None:
    """값 바로 뒤 괄호 → 같은 문장 → 같은 최상위 절의 앞 문장 순서로 설치 장소를 찾는다."""
    for source in (value.cond_raw, text, preceding):
        if source and (m := SITE.findall(source)):
            return re.sub(r"\s+", "", m[-1] if source is preceding else m[0]).replace(
                "kV변전소", "kV 변전소")
    return None


# ---------------------------------------------------------------- 한 요구사항

def _heading_key(c: Candidate, parent, dicts: Dictionaries) -> str | None:
    """하위 항목의 항목키는 바로 위 소제목 행("1) Continuous current") → 상위 항목 순서로 찾는다."""
    rows = c.table.rows
    index = next(i for i, row in enumerate(rows) if row is c.row)
    stop = c.row.parent_index if c.row.parent_index is not None else index
    for row in reversed(rows[stop + 1:index]):
        if not (row.item_no or "").strip() and not (row.required or "").strip():
            return item_key_of(row.item_name, dicts)
    return item_key_of(parent.item_name, dicts) if parent else None


def normalize_candidate(c: Candidate, sections: list[Section], dicts: Dictionaries,
                        doc_target: str | None, preceding_text: str = "") -> list[Value]:
    if c.req_kind != "REQUIREMENT":
        return []
    if c.row is not None and c.table is not None and c.table.is_datasheet:
        parent = c.table.rows[c.row.parent_index] if c.row.parent_index is not None else None
        # "- Feeder bays"의 단위 칸이 비면 상위 항목("Rated normal current / A")의 단위다.
        unit = c.row.unit or (parent.unit if parent else None)
        values = cell_values(c.row.required, unit)
        name = c.row.item_name
        key = item_key_of(name, dicts)
        if key is None:
            key = _heading_key(c, parent, dicts)
        if not unit_fits(key, unit):
            key = None
        cond = TIME_CONDITION.search(name or "") or re.search(
            r"\((\d+(?:\.\d+)?)\s*seconds?\)", name or "", re.IGNORECASE)
        for v in values:
            v.item_key = key
            if cond:
                v.cond_time_s = float(cond.group(1))
            v.basis_standard = standard_of(c.row.required) if v.cell_form != "DELEGATED" else None
            v.target_object = context_target(c, sections, dicts, doc_target)
            # 데이터시트 하나는 설비 하나다 (파일 1의 TS-230-GIS와 TS-115-GIS는 다른 설비).
            v.equipment_key = f"{v.target_object}|{table_label(c.table)}"
        return values

    values = sentence_values(c.text)
    if not values:
        return []
    target = context_target(c, sections, dicts, doc_target)
    std = standard_of(c.text)
    for v in values:
        # 한 단락에 값이 여럿이면 값이 든 문장에서 항목·대상·규격을 먼저 찾는다
        # ("압력저하는 3 % 이내 … 또 가스 누설량이 연간 1 % 이내").
        clause = clause_at(c.text, v.pos)
        key = item_key_of(clause, dicts, contains=True)
        if not unit_fits(key, v.unit_raw):
            key = None
        v.item_key = key or UNIT_ITEM_FALLBACK.get((v.unit_raw or "").lower())
        v.target_object = target_of(clause, dicts) or target
        v.basis_standard = standard_of(clause) or std
        site = site_of(v, c.text, preceding_text)
        if target and site:
            v.equipment_key = f"{target}|{site}"
    return values
