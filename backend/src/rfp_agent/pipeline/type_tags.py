"""FR-04 유형 표시. 유형 규칙표가 먼저, AI는 규칙에 안 걸린 줄만."""

import re
from dataclasses import dataclass

from rfp_agent.pipeline.extract import Candidate


@dataclass
class TypeRule:
    rule_id: int | None
    rule_code: str
    pattern: str
    type_code: str
    match_kind: str
    priority: int

    def matches(self, text: str) -> bool:
        if self.match_kind == "REGEX":
            return re.search(self.pattern, text) is not None
        word = rf"(?<!\w){re.escape(self.pattern)}(?!\w)"
        return re.search(word, text, re.IGNORECASE) is not None


@dataclass
class TypeTag:
    type_code: str
    is_primary: bool
    decided_by: str
    rule: TypeRule | None


NUMERIC_ROW_PRIORITY = 70


def tag(candidate: Candidate, rules: list[TypeRule], risk_terms: list[re.Pattern]) -> list[TypeTag]:
    text = candidate.text
    hits: list[tuple[int, str, TypeRule | None]] = []
    for rule in rules:
        if rule.matches(text):
            hits.append((rule.priority, rule.type_code, rule))
    if any(p.search(text) for p in risk_terms):
        hits.append((1, "RISK", None))
    row = candidate.row
    if row and row.unit and row.required and re.search(r"\d", row.required):
        hits.append((NUMERIC_ROW_PRIORITY, "TECH_PERF", None))
    hits.sort(key=lambda h: (h[0], h[1]))
    tags: list[TypeTag] = []
    for _, code, rule in hits:
        if any(t.type_code == code for t in tags):
            continue
        tags.append(TypeTag(code, is_primary=not tags, decided_by="RULE", rule=rule))
    return tags
