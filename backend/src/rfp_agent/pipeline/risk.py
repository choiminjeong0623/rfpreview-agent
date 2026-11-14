"""FR-06 위험 조건 후보. 후보 고르기는 코드, 설명 문장은 AI, 확정은 사람 (CR-08)."""

import re
from dataclasses import dataclass, field
from itertools import combinations

# 위험 표현이 후보가 되는 조항 (절 제목에 이 말이 있어야 한다)
CONTEXT_WORDS = {
    "BLANKET": r"deviation|exception|clarification|contract|condition|일탈|예외|계약|조건",
    "COST_SHIFT": r"scope|supply|change|variation|공급|변경",
    "OPEN_SCOPE": r"scope|supply|공급\s*범위|범위",
}
# 사전의 표현 → 찾는 정규식 (표현마다 특별한 조건)
SPECIAL_PATTERNS = {
    "no deviation(s)": r"\bno deviations?\b",
    "본다": r"것으로\s*본다",
}
FLAG_KIND = {"BLANKET": "BLANKET", "COST_SHIFT": "BLANKET", "OPEN_SCOPE": "OPEN_SCOPE"}


@dataclass
class RiskExpression:
    expr_id: int | None
    expression: str
    language: str
    risk_kind: str

    @property
    def pattern(self) -> re.Pattern:
        if self.expression in SPECIAL_PATTERNS:
            return re.compile(SPECIAL_PATTERNS[self.expression], re.IGNORECASE)
        if self.language == "ko":
            return re.compile(re.escape(self.expression))
        return re.compile(rf"\b{re.escape(self.expression)}\b", re.IGNORECASE)


@dataclass
class ValueRef:
    """값 불일치 비교에 쓰는 값 하나와 그 근거."""

    key: object                 # 저장 쪽에서 쓰는 식별자 (요구사항 id, 값 id 등)
    requirement_key: object
    document_key: object
    project_key: str | None
    item_key: str
    num_value: float
    unit: str | None
    target_object: str | None
    basis_standard: str | None
    equipment_key: str | None
    location: str               # "파일 6 174행"
    raw_text: str | None
    table_key: object = None    # 데이터시트 표에서 온 값이면 그 표
    seq: int = 1                # 한 칸에 값이 여럿("360/360/75")이면 몇 번째인지
    row_label: str | None = None  # 데이터시트 행 이름 (문서를 넘어 표끼리는 같은 행만 비교)
    multi: bool = False


@dataclass
class RiskCandidate:
    risk_kind: str
    members: list[object]                  # 요구사항 key 목록
    value_members: list[object] = field(default_factory=list)
    expression: RiskExpression | None = None
    item_key: str | None = None
    facts: str = ""


def scope_words_in(titles: list[str], risk_kind: str) -> bool:
    pattern = CONTEXT_WORDS[risk_kind]
    return any(re.search(pattern, t, re.IGNORECASE) for t in titles)


def find_clause_risks(text: str, section_titles: list[str],
                      expressions: list[RiskExpression]) -> list[RiskExpression]:
    """문장 하나에서 후보가 되는 위험 표현을 돌려준다. 조항 위치 조건이 맞을 때만."""
    hits = []
    for expr in expressions:
        if expr.pattern.search(text) and scope_words_in(section_titles, expr.risk_kind):
            hits.append(expr)
    return hits


def _unit(u: str | None) -> str:
    return re.sub(r"\s+", "", (u or "").lower()).replace("℃", "°c").replace("degc", "°c")


def targets_related(a: str | None, b: str | None, parents: dict[str, str]) -> bool:
    if a is None or b is None:
        return a == b
    return a == b or parents.get(a) == b or parents.get(b) == a


def find_value_mismatches(values: list[ValueRef], parents: dict[str, str]) -> list[RiskCandidate]:
    groups: dict[tuple, list[ValueRef]] = {}
    for v in values:
        scope = ("P", v.project_key) if v.project_key else ("D", v.document_key)
        groups.setdefault((scope, v.item_key, _unit(v.unit)), []).append(v)

    out = []
    for (_, item_key, _), group in sorted(groups.items(), key=lambda kv: str(kv[0])):
        seen_pairs: set[tuple] = set()
        for a, b in combinations(group, 2):
            if a.requirement_key == b.requirement_key or a.num_value == b.num_value:
                continue
            if not targets_related(a.target_object, b.target_object, parents):
                continue
            if (a.multi or b.multi) and not (a.multi and b.multi and a.seq == b.seq):
                continue        # "360/360/75"는 같은 자리 값끼리만 비교한다
            same_doc = a.document_key == b.document_key
            both_tables = a.table_key is not None and b.table_key is not None
            if not same_doc and both_tables and a.row_label != b.row_label:
                continue
            if same_doc and both_tables:
                # 같은 문서의 데이터시트끼리는 비교하지 않는다. 표 하나가 설비 하나이고
                # (파일 1 TS-AUTO-TR 360 MVA / 240 MVA), 한 표 안의 두 행은 서로 다른 항목이다.
                continue
            if same_doc:
                # 같은 문서라도 장소가 다르게 적힌 값은 다른 설비다
                # (5 kVA 수상전기실 / 10 kVA 154kV 변전소).
                if a.equipment_key and b.equipment_key and a.equipment_key != b.equipment_key:
                    continue
            elif not (a.equipment_key and a.equipment_key == b.equipment_key):
                continue        # 문서를 넘을 때는 "설비 이름 + 설치 장소"가 같아야 한다
            pair = tuple(sorted([str(a.requirement_key), str(b.requirement_key)]))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            out.append(RiskCandidate(
                risk_kind="VALUE_MISMATCH", members=[a.requirement_key, b.requirement_key],
                value_members=[a.key, b.key], item_key=item_key, facts=mismatch_facts(a, b),
            ))
    return out


def _describe(v: ValueRef) -> str:
    site = v.equipment_key.split("|", 1)[1] if v.equipment_key else None
    extra = "".join(f", {x}" for x in (site, v.basis_standard) if x)
    return f"{v.location}: {v.raw_text} ({v.target_object or '대상 미상'}{extra})"


def mismatch_facts(a: ValueRef, b: ValueRef) -> str:
    lines = [_describe(a), _describe(b)]
    target_diff = a.target_object != b.target_object
    std_diff = bool(a.basis_standard and b.basis_standard and a.basis_standard != b.basis_standard)
    if target_diff and std_diff:
        lines.append("적용 대상과 근거 규격이 다름")
    elif target_diff:
        lines.append("적용 대상이 다름")
    elif std_diff:
        lines.append("근거 규격이 다름")
    return "\n".join(lines)
