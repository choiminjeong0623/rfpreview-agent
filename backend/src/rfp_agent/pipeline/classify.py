"""FR-01 문서 분류. 파일명과 첫 장 표현(문서 종류 규칙 사전)으로 코드가 정하고,
AI는 첫 장 요약으로 보조한다.
"""

import re
from dataclasses import dataclass

from rfp_agent.pipeline.docx_reader import Block

FIRST_PAGE_BLOCKS = 60
MIN_READABLE_LINES = 10

STANDARD_PATTERNS = {
    "IEC": r"\bIEC\b",
    "IEEE_UL": r"\b(?:IEEE|ANSI|UL|NEMA|NFPA)\b",
    "KS_ES": r"\bKS [A-Z]\b|\bES-\d|한전",
}
MIN_STANDARD_MENTIONS = 3
MIXED_RATIO = 0.5


@dataclass
class KindRule:
    """문서 종류 규칙 사전 한 줄 (doc_kind_rule, data/seed/doc_kind_rules.csv)."""
    doc_kind: str
    name_pattern: str               # 소문자 파일 이름에서 찾는다
    page_pattern: str | None        # 첫 장에서 대소문자 무시로 찾는다


def load_kind_rules(conn) -> list[KindRule]:
    """적재된 문서 종류 규칙을 순서대로 읽는다. 위에서부터 먼저 맞는 줄이 이긴다."""
    return [KindRule(*r) for r in conn.execute(
        "SELECT doc_kind, name_pattern, page_pattern FROM doc_kind_rule ORDER BY priority")]


@dataclass
class CatalogEntry:
    file_no: int
    file_key: str
    bundle: str
    language: str
    project_key: str | None


@dataclass
class Classification:
    file_no: int | None
    bundle: str
    doc_kind: str
    project_key: str | None
    language: str
    standard_system: str | None
    judge_target: bool
    readable: bool
    rule_id: str
    needs_review: bool = False
    ai_doc_kind: str | None = None
    classify_by: str = "RULE"


def find_catalog(file_name: str, catalog: list[CatalogEntry]) -> CatalogEntry | None:
    hits = [c for c in catalog if c.file_key.lower() in file_name.lower()]
    # 더 긴 표현이 더 구체적이다 (예: "115kV GIS" 보다 "RFP06 154kV GIS Specification … 154kV GIS")
    return max(hits, key=lambda c: len(c.file_key)) if hits else None


def doc_kind_of(file_name: str, first_page: str, rules: list[KindRule]) -> tuple[str, str]:
    """파일 이름 표현을 모두 본 뒤 첫 장 표현을 본다. 맞는 줄이 없으면 종류 모름."""
    name = file_name.lower()
    for r in rules:
        if re.search(r.name_pattern, name):
            return r.doc_kind, f"K-NAME-{r.doc_kind}"
    for r in rules:
        if r.page_pattern and re.search(r.page_pattern, first_page, re.IGNORECASE):
            return r.doc_kind, f"K-PAGE-{r.doc_kind}"
    return "UNKNOWN", "K-NONE"


def standard_system_of(text: str) -> str | None:
    counts = {k: len(re.findall(p, text)) for k, p in STANDARD_PATTERNS.items()}
    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    (top, top_n), (_, second_n) = ranked[0], ranked[1]
    if top_n < MIN_STANDARD_MENTIONS:
        return None
    return "MIXED" if second_n >= top_n * MIXED_RATIO else top


def language_of(text: str) -> str:
    hangul = len(re.findall(r"[가-힣]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    return "ko" if hangul > latin * 0.5 else "en"


def first_page_text(blocks: list[Block]) -> str:
    return "\n".join(b.text for b in blocks[:FIRST_PAGE_BLOCKS])


def classify(file_name: str, blocks: list[Block], catalog: list[CatalogEntry],
             kind_rules: list[KindRule]) -> Classification:
    full_text = "\n".join(b.text for b in blocks)
    nonempty = sum(1 for b in blocks if b.text.strip())
    readable = nonempty >= MIN_READABLE_LINES
    entry = find_catalog(file_name, catalog)
    kind, rule_id = doc_kind_of(file_name, first_page_text(blocks), kind_rules)
    if entry:
        bundle, project_key, language = entry.bundle, entry.project_key, entry.language
    else:
        # 파일 목록에 없는 문서는 판정하지 않는 묶음(C)으로 두고 사람이 확인한다.
        bundle, project_key, language = "C", None, language_of(full_text)
    if not readable:
        language = "image"
    return Classification(
        file_no=entry.file_no if entry else None,
        bundle=bundle,
        doc_kind=kind,
        project_key=project_key,
        language=language,
        standard_system=standard_system_of(full_text) if readable else None,
        judge_target=bundle in ("A", "B") and readable,
        readable=readable,
        rule_id=rule_id,
        needs_review=entry is None or kind == "UNKNOWN",
    )


def apply_ai_kind(result: Classification, ai_kind: str | None) -> Classification:
    """AI 보조 판단을 붙인다. 규칙과 다르면 '확인 필요'."""
    if ai_kind is None:
        return result
    result.ai_doc_kind = ai_kind
    if result.doc_kind == "UNKNOWN":
        # 규칙이 못 정한 종류만 AI 판단을 쓰고, 그래도 사람이 확인한다.
        result.doc_kind, result.classify_by = ai_kind, "AI"
    if ai_kind != result.doc_kind or result.classify_by == "AI":
        result.needs_review = True
    return result


def suggest_bundle(result: Classification, in_catalog: bool) -> tuple[str, str]:
    """분석 전 추천 묶음과 이유 (등록 화면용, 저장하지 않는다).

    문서 목록에 있으면 목록 묶음. 없으면 읽을 수 있는 IEC 문서만 판정 묶음(B)으로 추천한다
    (제품표가 IEC 정격). A는 사업 데이터시트라 목록으로만 정하고, D는 자동으로 고르지 않는다.
    """
    if in_catalog:
        return result.bundle, f"문서 목록의 묶음 {result.bundle}"
    if not result.readable:
        return "C", "글자를 읽지 못함 (스캔 문서)"
    if result.standard_system == "IEC":
        return "B", "문서 목록에 없음 · IEC 규격 문서라 판정 대상으로 추천"
    system = {"IEEE_UL": "IEEE·UL", "KS_ES": "한국 규격", "MIXED": "여러 규격"}.get(
        result.standard_system or "", "주 규격 체계 모름")
    return "C", f"문서 목록에 없음 · {system}이라 판정하지 않음"


def apply_choice(result: Classification, bundle: str | None,
                 doc_kind: str | None) -> Classification:
    """사람이 등록 화면에서 정한 묶음·문서 종류를 붙인다. 규칙 결과와 같으면 그대로 둔다."""
    bundle = bundle or result.bundle
    doc_kind = doc_kind or result.doc_kind
    if (bundle, doc_kind) == (result.bundle, result.doc_kind):
        return result
    result.bundle, result.doc_kind, result.classify_by = bundle, doc_kind, "HUMAN"
    result.judge_target = bundle in ("A", "B") and result.readable
    result.needs_review = False
    return result
