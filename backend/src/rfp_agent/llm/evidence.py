"""AI 설명의 근거 조각: ID(E-문서-위치)를 붙여 AI에 주고, 돌아온 ID·인용을 코드가 대조한다."""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class EvidenceSpan:
    evidence_id: str
    text: str


def evidence_id(document_id: int, location_id: int) -> str:
    return f"E-{document_id}-{location_id}"


def parse_evidence_id(value: str) -> tuple[int, int] | None:
    match = re.fullmatch(r"E-(\d+)-(\d+)", value)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def normalize_quote(text: str) -> str:
    """공백 차이를 제외한 원문 인용문 비교."""
    return re.sub(r"\s+", " ", text).strip()
