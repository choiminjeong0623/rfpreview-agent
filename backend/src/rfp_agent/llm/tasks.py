"""언어 모델에 맡기는 일 4가지. 모두 '보조'이고, 결과는 코드가 검증한다."""

import re
from collections.abc import Callable
from dataclasses import dataclass

from rfp_agent.llm.client import LLM, LLMFormatError, call_with_retry
from rfp_agent.llm.evidence import EvidenceSpan, normalize_quote
from rfp_agent.llm.parallel import run_ordered, workers_of

# p6: 문서 종류에 물량표(BOQ) (add-boq-processor). p5: 문서 종류 설명 (add-document-processors).
# p4: 유형 질문에 사람이 고른 예 (add-type-examples). p3: 절·표 문맥
PROMPT_VERSION = "p6"
DOC_KINDS = ["BID_FORM", "REQUIREMENT_SPEC", "PURCHASE_SPEC", "TEST_SPEC", "SUPPLIER_SPEC",
             "BOQ", "UNKNOWN"]
SENTENCE_LABELS = ["REQUIREMENT", "WRITING_RULE", "DESCRIPTION"]
TYPE_CODES = ["TECH_PERF", "RISK", "STANDARD_CERT", "COST", "TEST", "MAKER_QUAL", "SITE_ENV",
              "NONE"]
CHUNK = 40

Progress = Callable[[int, int], None]      # (끝난 줄 수, 전체 줄 수) — 처리 상태 화면용


def one_line(text: str) -> str:
    """번호 매긴 목록이 깨지지 않게 줄바꿈을 없앤다."""
    return re.sub(r"\s+", " ", text).strip()


def classify_document(llm: LLM, file_name: str, first_page: str) -> str:
    prompt = (
        "다음은 전력 설비 입찰 RFP 문서의 파일명과 첫 장이다. 문서 종류를 하나 고른다.\n"
        "BID_FORM=입찰 서식, REQUIREMENT_SPEC=요구 사양, PURCHASE_SPEC=구매 사양, "
        "TEST_SPEC=시험 사양, SUPPLIER_SPEC=공급사 사양·답안, BOQ=물량표(품목·수량 표), "
        "UNKNOWN=모름.\n"
        f"파일명: {file_name}\n첫 장:\n{first_page[:4000]}"
    )
    schema = {"type": "object", "properties": {"doc_kind": {"type": "string", "enum": DOC_KINDS}},
              "required": ["doc_kind"]}

    def check(d):
        assert d["doc_kind"] in DOC_KINDS

    return call_with_retry(llm, prompt, schema, check)["doc_kind"]


def _numbered_schema(field: str, key: str, value: dict) -> dict:
    """답마다 묻는 글의 줄 번호(n)를 함께 받는 스키마 (update-ai-answer-checks)."""
    return {"type": "object", "properties": {field: {"type": "array", "items": {
        "type": "object", "properties": {"n": {"type": "integer"}, key: value},
        "required": ["n", key]}}}, "required": [field]}


def _check_numbers(answers: list[dict], count: int, field: str) -> None:
    """줄 번호가 0..count-1을 하나씩 빠짐없이 덮어야 한다. 개수만 맞고 번호가 겹치면 실패."""
    numbers = sorted(x["n"] for x in answers)
    assert numbers == list(range(count)), f"{field} 번호 {numbers[:5]}…, 필요 0~{count - 1}"


def _in_order(answers: list[dict]) -> list[dict]:
    return sorted(answers, key=lambda x: x["n"])


def _pick_each(llm: LLM, items: list[str], field: str, choices: list[str], prompt_of) -> list[str]:
    """항목마다 보기 하나를 고르게 한다. 답의 개수가 틀리면 묶음을 반으로 나눠 다시 묻는다.

    모델이 긴 목록에서 한두 개를 빠뜨리면 같은 질문을 되풀이해도 같은 답이 나온다(temperature 0).
    그래서 형식 오류면 다시 묻지 않고 바로 둘로 나눈다. 한 개짜리도 실패하면 그대로 실패로 둔다.
    연결 오류는 재시도(CR-12) 뒤 나누지 않고 바로 실패한다 (update-llm-retry-kinds).
    """
    prompt = prompt_of(items)
    schema = _numbered_schema(field, "v", {"type": "string", "enum": choices})

    def check(d):
        _check_numbers(d[field], len(items), field)
        assert all(x["v"] in choices for x in d[field])

    try:
        return [x["v"] for x in _in_order(call_with_retry(llm, prompt, schema, check)[field])]
    except LLMFormatError:
        if len(items) == 1:
            raise
        half = len(items) // 2
        return (_pick_each(llm, items[:half], field, choices, prompt_of)
                + _pick_each(llm, items[half:], field, choices, prompt_of))


def _hint_line(doc_hint: str | None) -> str:
    """질문 첫 줄: 문서 처리기의 문서 종류 설명 (없으면 빈 글자)."""
    return f"문서 종류: {doc_hint}\n" if doc_hint else ""


def _label_prompt(section_title: str | None, part: list[str],
                  doc_hint: str | None = None) -> str:
    numbered = "\n".join(f"{i}. {one_line(s)[:600]}" for i, s in enumerate(part))
    return _hint_line(doc_hint) + (
        "RFP의 한 절에서 뽑은 문장들이다. "
        "각 문장이 입찰자가 지켜야 할 요구사항(REQUIREMENT)인지, "
        "제출 양식을 채우는 방법에 대한 작성 규칙(WRITING_RULE)인지, "
        "설명(DESCRIPTION)인지 고른다. "
        "문장마다 앞의 번호(n)와 고른 label(v)을 함께 낸다.\n"
        f"절 제목: {section_title or '(없음)'}\n{numbered}"
    )


def _pick_chunks(llm: LLM, chunks: list[tuple[list[str], Callable[[list[str]], str]]],
                 field: str, choices: list[str], total: int,
                 on_progress: Progress | None) -> list[list[str]]:
    """40줄 묶음들을 동시에 묻는다(NFR-10). 결과는 묶음 순서, 진행은 묶음이 끝날 때마다."""
    done = 0

    def finished(i: int, _labels: list[str]) -> None:
        nonlocal done
        done += len(chunks[i][0])
        if on_progress:
            on_progress(done, total)

    jobs = [lambda part=part, prompt_of=prompt_of: _pick_each(llm, part, field, choices,
                                                              prompt_of)
            for part, prompt_of in chunks]
    return run_ordered(jobs, workers_of(llm), finished)


def label_sections(llm: LLM, sections: list[tuple[str | None, list[str]]],
                   on_progress: Progress | None = None,
                   doc_hint: str | None = None) -> list[list[str]]:
    """절마다 문장에 요구사항 / 작성 규칙 / 설명 중 하나를 붙인다.

    묻는 글은 절 하나의 40줄 묶음 단위(차례로 할 때와 같음)이고,
    모든 절의 묶음을 함께 동시에 보낸다.
    """
    chunks, owner = [], []
    for n, (title, sentences) in enumerate(sections):
        for start in range(0, len(sentences), CHUNK):
            chunks.append((sentences[start:start + CHUNK],
                           lambda part, t=title: _label_prompt(t, part, doc_hint)))
            owner.append(n)
    total = sum(len(s) for _, s in sections)
    answers = _pick_chunks(llm, chunks, "labels", SENTENCE_LABELS, total, on_progress)
    out: list[list[str]] = [[] for _ in sections]
    for n, labels in zip(owner, answers, strict=True):
        out[n].extend(labels)
    return out


def label_sentences(llm: LLM, section_title: str | None, sentences: list[str],
                    on_progress: Progress | None = None) -> list[str]:
    """절 하나의 문장마다 요구사항 / 작성 규칙 / 설명 중 하나를 붙인다."""
    return label_sections(llm, [(section_title, sentences)], on_progress)[0]


CONTEXT_CHARS = 120


def _with_context(text: str, context: str | None) -> str:
    """'[절 3.2 Leakage · 표 TS-154-GIS] 문장'. 문맥이 없으면 문장만."""
    line = one_line(text)[:400]
    return f"[{one_line(context)[:CONTEXT_CHARS]}] {line}" if context else line


def _with_examples(line: str, examples: list[tuple[str, str]]) -> str:
    """줄 끝에 다른 문서에서 사람이 고른 예 (add-type-examples). 한 줄 안에 둔다."""
    if not examples:
        return line
    shown = "; ".join(f'"{text}" → {code}' for text, code in examples)
    return f"{line} (사람이 고른 예: {shown})"


def type_unclassified(llm: LLM, texts: list[str], on_progress: Progress | None = None,
                      contexts: list[str | None] | None = None,
                      examples: list[list[tuple[str, str]]] | None = None,
                      doc_hint: str | None = None) -> list[str]:
    """규칙에 안 걸린 요구사항마다 유형 하나. contexts는 줄마다 절·표 제목 문맥(없으면 None).

    examples는 줄마다 다른 문서에서 사람이 고친 비슷한 줄과 유형(참고, add-type-examples).
    """
    lines = [_with_examples(_with_context(t, c), e) for t, c, e in zip(
        texts, contexts or [None] * len(texts), examples or [[]] * len(texts), strict=True)]

    def prompt_of(part: list[str]) -> str:
        numbered = "\n".join(f"{i}. {line}" for i, line in enumerate(part))
        return _hint_line(doc_hint) + (
            "RFP 요구사항마다 유형 하나를 고른다. 대괄호 안은 그 줄이 속한 절·표 제목(문맥)이다. "
            "TECH_PERF=기술 성능, RISK=위험 조건, "
            "STANDARD_CERT=적용 규격·인증, COST=비용 영향, TEST=시험, MAKER_QUAL=제조사 자격, "
            "SITE_ENV=설치 환경, NONE=어느 것도 아님. 괄호 안 '사람이 고른 예'는 다른 문서에서 "
            "엔지니어가 비슷한 줄에 고른 유형으로 참고만 한다. 요구사항마다 앞의 번호(n)와 "
            "고른 유형(v)을 함께 낸다.\n" + numbered
        )

    chunks = [(lines[start:start + CHUNK], prompt_of) for start in range(0, len(lines), CHUNK)]
    answers = _pick_chunks(llm, chunks, "types", TYPE_CODES, len(lines), on_progress)
    return [code for part in answers for code in part]


NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
RELATIONS = ["DIRECT", "DERIVED", "INFERRED"]


@dataclass(frozen=True)
class Claim:
    """설명 문장 하나와 그 근거: 고른 근거 조각 ID와 그 조각에서 그대로 옮긴 인용."""
    text: str
    quote: str
    evidence_ids: tuple[str, ...]
    relation: str


@dataclass(frozen=True)
class RiskExplanation:
    text: str
    claims: tuple[Claim, ...]
    verdicts: tuple[str, ...] = ()      # 문장마다 검증 답 YES/NO/UNSURE (add-claim-verifier)

    @property
    def check(self) -> str | None:
        """모든 문장이 YES면 VERIFIED, 아니면 NEEDS_REVIEW. 검증하지 않았으면 None."""
        if not self.verdicts:
            return None
        return "VERIFIED" if all(v == "YES" for v in self.verdicts) else "NEEDS_REVIEW"


# 근거 대조에서 설명을 버린 이유 (update-ai-answer-checks). 처음 걸린 것 하나만 남긴다.
UNKNOWN_EVIDENCE = "UNKNOWN_EVIDENCE"       # 주지 않은 근거 ID
QUOTE_NOT_FOUND = "QUOTE_NOT_FOUND"         # 인용이 고른 근거 조각에 없음
NUMBER_NOT_ALLOWED = "NUMBER_NOT_ALLOWED"   # 사실·그 문장의 근거 조각에 없는 숫자·배수 말
FORMAT_ERROR = "FORMAT_ERROR"               # 형식이 틀린 답 (다시 묻지 않음)


@dataclass(frozen=True)
class DroppedExplanation:
    reason: str


# 숫자 없이 크기를 말하는 배수·분수 말. 근거·사실에 같은 말이 없으면 지어낸 크기로 본다.
QUANTITY_WORDS = re.compile(r"(?:두|세|네|다섯|열)\s?배|절반|\b(?:twice|double|triple|half)\b",
                            re.IGNORECASE)


def _quantity_words(text: str) -> set[str]:
    return {re.sub(r"\s", "", w).lower() for w in QUANTITY_WORDS.findall(text)}


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in NUMBER.findall(text)}


def explain_risk(llm: LLM, kind: str, facts: str,
                 spans: list[EvidenceSpan]) -> RiskExplanation | DroppedExplanation:
    """위험 조건 설명을 문장(claim)마다 근거 조각 ID·원문 인용과 함께 받는다.

    코드가 검증해서 하나라도 어긋나면 설명 전체를 버리고 이유를 돌려준다 (CR-07):
    없는 근거 ID, 고른 조각에 없는 인용, 사실과 그 문장이 댄 근거 조각에 없는 숫자·배수 말.
    """
    prompt = (
        "입찰 기술 검토 엔지니어에게 이 조항이 왜 위험한지, 또는 두 값이 왜 다를 수 있는지 "
        "한국어 두세 문장으로 설명한다. 아래 근거 조각만 쓰고, 근거에 없는 사실이나 숫자는 "
        "쓰지 않는다. 문장마다 쓴 근거 조각 ID(evidence_ids), 그 조각에서 그대로 옮긴 "
        "짧은 인용(exact_quote), 근거와의 관계(relation: DIRECT 그대로, DERIVED 계산·비교, "
        "INFERRED 추론)를 함께 낸다.\n"
        f"종류: {kind}\n사실:\n{facts}\n근거:\n"
        + "\n".join(f"[{s.evidence_id}] {s.text[:800]}" for s in spans)
    )
    schema = {"type": "object", "properties": {"claims": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "exact_quote": {"type": "string"},
            "evidence_ids": {"type": "array", "items": {"type": "string"}},
            "relation": {"type": "string", "enum": RELATIONS},
        },
        "required": ["text", "exact_quote", "evidence_ids", "relation"]}}},
        "required": ["claims"]}

    def check(d):
        assert d["claims"]
        for c in d["claims"]:
            assert c["text"].strip() and c["exact_quote"].strip() and c["evidence_ids"]
            assert c["relation"] in RELATIONS

    try:
        data = call_with_retry(llm, prompt, schema, check)
    except LLMFormatError:
        return DroppedExplanation(FORMAT_ERROR)  # 후보는 남고 처리는 계속된다
    sources = {s.evidence_id: s.text[:800] for s in spans}
    claims = tuple(Claim(c["text"].strip(), c["exact_quote"].strip(), tuple(c["evidence_ids"]),
                         c["relation"]) for c in data["claims"])
    for c in claims:
        if any(i not in sources for i in c.evidence_ids):
            return DroppedExplanation(UNKNOWN_EVIDENCE)
        quote = normalize_quote(c.quote)
        if not any(quote in normalize_quote(sources[i]) for i in c.evidence_ids):
            return DroppedExplanation(QUOTE_NOT_FOUND)
        # 숫자·배수 말은 사실과 이 문장이 댄 근거 조각에 있어야 한다 (다른 조각의 숫자는 안 됨)
        basis = facts + " " + " ".join(sources[i] for i in c.evidence_ids)
        if (not _numbers(c.text) <= _numbers(basis)
                or not _quantity_words(c.text) <= _quantity_words(basis)):
            return DroppedExplanation(NUMBER_NOT_ALLOWED)
    return RiskExplanation("\n".join(c.text for c in claims), claims)


VERDICTS = ["YES", "NO", "UNSURE"]


def check_support(llm: LLM, claims: tuple[Claim, ...], sources: dict[str, str]) -> list[str]:
    """검증 에이전트 (add-claim-verifier): 문장마다 인용·근거 조각이 그 문장을 받쳐 주는지.

    설명을 쓴 질문과 다른 질문으로 묻고, 사실 문장은 주지 않아 원문으로만 판단하게 한다.
    결과는 표시만 한다(CR-01·08). 형식 오류는 다시 묻지 않고 모두 UNSURE.
    """
    numbered = "\n".join(
        f"{i}. 문장({c.relation}): {one_line(c.text)} / 인용: {one_line(c.quote)} / 근거: "
        + " | ".join(f"[{e}] {one_line(sources.get(e, ''))[:800]}" for e in c.evidence_ids)
        for i, c in enumerate(claims))
    prompt = (
        "너는 검토 엔지니어를 돕는 검증자다. 아래 문장마다, 함께 준 인용과 근거 원문만 보고 "
        "판단한다. 괄호 안은 문장이 근거와 맺는 관계다. DIRECT·DERIVED 문장은 근거에 그 내용이 "
        "있거나 근거 값으로 바로 따라 나오면 YES. INFERRED 문장은 입찰자에게 미칠 영향을 "
        "추론한 것이므로, 근거에서 무리 없이 나오는 추론이고 근거에 없는 사실·숫자·조건을 "
        "더하지 않았으면 YES. 근거와 어긋나거나 근거에 없는 사실을 더했으면 NO, 근거만으로 "
        "판단할 수 없으면 UNSURE. "
        "문장마다 앞의 번호(n)와 판단(v)을 함께 낸다.\n" + numbered
    )
    schema = _numbered_schema("verdicts", "v", {"type": "string", "enum": VERDICTS})

    def check(d):
        _check_numbers(d["verdicts"], len(claims), "verdicts")
        assert all(x["v"] in VERDICTS for x in d["verdicts"])

    try:
        return [x["v"] for x in _in_order(call_with_retry(llm, prompt, schema, check)["verdicts"])]
    except LLMFormatError:
        return ["UNSURE"] * len(claims)


DRAFT_VERSION = "d1"
COMPETITOR = re.compile(r"경쟁|타사|다른 회사|competitor|other manufacturer", re.IGNORECASE)
_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def _usable_draft(text: str, marks: dict[str, str]) -> bool:
    """비지 않고, 경쟁 비교가 없고, 준 자리표시자를 모두(그리고 그것만) 썼다."""
    return (bool(text) and not COMPETITOR.search(text)
            and set(_PLACEHOLDER.findall(text)) == set(marks))


def draft_sentences(llm: LLM, purpose: str,
                    items: list[tuple[str, dict[str, str]]]) -> list[str | None]:
    """항목마다 한국어 문장 하나. 숫자는 자리표시자로만 쓰게 하고(CR-07) 채우기·대조는 코드가 한다.

    items: (사실 문장, {자리표시자: 뜻}) 목록.
    준 자리표시자를 다 쓰지 않았거나 없는 자리표시자를 썼거나, 비었거나, 경쟁 제품 비교가 있는
    줄은 None이다. 부르는 곳이 그 줄만 코드 기본 문장으로 바꾼다 (update-ai-answer-checks).
    줄 번호가 빠지거나 겹치면 형식 오류로 다시 묻는다 (CR-12).
    """

    def ask(part: list[tuple[str, dict[str, str]]]) -> list[str | None]:
        numbered = "\n".join(
            f"{i}. {one_line(facts)} (자리표시자: "
            + ", ".join(f"{{{k}}}={v}" for k, v in marks.items()) + ")"
            for i, (facts, marks) in enumerate(part))
        prompt = (
            f"입찰 기술 검토 엔지니어가 쓸 {purpose} 문장 초안을 "
            "항목마다 한국어 한두 문장으로 쓴다. "
            "숫자와 제품 이름은 직접 쓰지 말고 주어진 자리표시자를 모두 그대로 쓴다. "
            "사실에 없는 내용을 더하지 않고, 경쟁 제품이나 다른 회사와 비교하는 말은 쓰지 않는다. "
            "항목마다 앞의 번호(n)와 문장(text)을 함께 낸다.\n" + numbered
        )
        schema = _numbered_schema("texts", "text", {"type": "string"})

        def check(d):
            _check_numbers(d["texts"], len(part), "texts")

        try:
            answers = _in_order(call_with_retry(llm, prompt, schema, check)["texts"])
        except LLMFormatError:
            return [None] * len(part)       # 그 묶음은 코드 기본 문장 (다시 묻지 않음)
        return [text if _usable_draft(text := a["text"].strip(), marks) else None
                for a, (_, marks) in zip(answers, part, strict=True)]

    # 40줄 묶음을 동시에 묻고 묶음 순서대로 잇는다 (NFR-10)
    jobs = [lambda part=items[start:start + CHUNK]: ask(part)
            for start in range(0, len(items), CHUNK)]
    return [t for part in run_ordered(jobs, workers_of(llm)) for t in part]


DEPT_VIEWS = {
    "COST": ("견적 담당", "비용·일정·보증·지체상금처럼 견적 금액이나 조건에 반영할 것이 있는지"),
    "QUALITY": ("품질 담당", "시험·성적서·인증·시험 입회처럼 품질 쪽에서 맞출 수 있는지"),
    "SALES": ("영업 담당", "고객과 협의하거나 계약·납기 조건으로 확인할 것이 있는지"),
}
ASK_MAX = 160
_DIGIT = re.compile(r"\d")
_HANGUL = re.compile(r"[가-힣]")


def usable_question(text: str) -> bool:
    """비지 않고, 160자 이하, 숫자 없음(CR-07), 경쟁 비교 없음, 한글 있음."""
    return (bool(text) and len(text) <= ASK_MAX and not _DIGIT.search(text)
            and not COMPETITOR.search(text) and bool(_HANGUL.search(text)))


def department_questions(llm: LLM, role: str, items: list[str]) -> list[str | None]:
    """협조 요청마다 받는 부서 관점의 확인할 점 한 문장 (add-handoff-questions, C4).

    숫자는 쓰지 못한다(요구사항 칸에 원문 그대로 있음). 검사에 걸린 줄은 None →
    부르는 곳이 부서 기본 문장으로 바꾼다. 줄 번호가 틀리면 형식 오류(다시 묻지 않음).
    """
    dept, view = DEPT_VIEWS[role]

    def ask(part: list[str]) -> list[str | None]:
        numbered = "\n".join(f"{i}. {one_line(text)[:600]}" for i, text in enumerate(part))
        prompt = (
            f"입찰 기술 검토 엔지니어가 {dept}에게 협조를 요청하는 메일을 쓴다. "
            f"요청마다 {dept}가 {view} 확인할 점을 한국어 한 문장으로 쓴다. "
            "숫자는 하나도 쓰지 않는다(숫자는 메일의 요구사항 칸에 원문 그대로 있다). "
            "요구사항에 없는 사실을 더하지 않고, 경쟁 제품이나 다른 회사와 비교하지 않는다. "
            "판정이나 결론을 내리지 말고 확인을 부탁하는 문장으로 쓴다. "
            "요청마다 앞의 번호(n)와 문장(text)을 함께 낸다.\n" + numbered
        )
        schema = _numbered_schema("asks", "text", {"type": "string"})

        def check(d):
            _check_numbers(d["asks"], len(part), "asks")

        answers = _in_order(call_with_retry(llm, prompt, schema, check)["asks"])
        return [text if usable_question(text := " ".join(a["text"].split())) else None
                for a in answers]

    jobs = [lambda part=items[start:start + CHUNK]: ask(part)
            for start in range(0, len(items), CHUNK)]
    return [t for part in run_ordered(jobs, workers_of(llm)) for t in part]


ASSISTANT_VERSION = "a1"
ASSISTANT_ACTIONS = ["search_requirements", "find_judgments", "get_requirement", "answer"]
JUDGMENT_RESULTS = ["COMPLY", "DEVIATION_CANDIDATE", "QUERY_CANDIDATE", "NEEDS_REVIEW",
                    "WARRANTY_TO_FILL"]


def assistant_step(llm: LLM, question: str, observations: str, can_search: bool) -> dict:
    """검토 도우미 한 단계 (add-review-assistant, FR-17).

    다음에 쓸 읽기 도구와 인자, 또는 답 문장(근거 번호 함께)을 JSON 하나로 받는다.
    도구를 실행하고 답을 검증하는 일은 코드(pipeline/assistant.py)가 한다.
    """
    tools = (
        "도구(읽기만 한다):\n"
        "- search_requirements: 이 검토 요구사항 원문에서 words(문서 언어로, 보통 영어 낱말)가 "
        "모두 들어간 줄. type_code로 유형을 거를 수 있다 "
        f"({', '.join(TYPE_CODES[:-1])}).\n"
        "- find_judgments: 이 검토의 판정. result로 판정 값을 거르고 "
        f"({', '.join(JUDGMENT_RESULTS)}), words로 항목 이름·원문을 거른다.\n"
        "- get_requirement: 근거 번호 하나(ref, 예: R12)의 원문.\n"
        "- answer: 답한다.\n"
    ) if can_search else "더 찾을 수 없다. action은 answer만 쓴다.\n"
    prompt = (
        "너는 입찰 기술 검토 엔지니어를 돕는 검토 도우미다. 값을 바꾸거나 판정하지 않고, "
        "도구가 돌려준 줄만 근거로 한국어로 짧게 답한다. 문장마다 쓴 근거 번호(evidence_ids, "
        "예: R12, J30)를 단다. 근거에 없는 사실이나 숫자는 쓰지 않는다. 근거가 없으면 "
        "sentences를 비운다.\n"
        + tools
        + f"질문: {one_line(question)[:500]}\n"
        + (f"지금까지 찾은 것:\n{observations}\n" if observations else "아직 찾은 것이 없다.\n")
    )
    actions = ASSISTANT_ACTIONS if can_search else ["answer"]
    schema = {"type": "object", "properties": {
        "action": {"type": "string", "enum": actions},
        "words": {"type": "string"},
        "type_code": {"type": "string", "enum": TYPE_CODES[:-1] + [""]},
        "result": {"type": "string", "enum": JUDGMENT_RESULTS + [""]},
        "ref": {"type": "string"},
        "sentences": {"type": "array", "items": {"type": "object", "properties": {
            "text": {"type": "string"},
            "evidence_ids": {"type": "array", "items": {"type": "string"}}},
            "required": ["text", "evidence_ids"]}},
    }, "required": ["action"]}

    def check(d):
        assert d["action"] in actions
        if d["action"] == "answer":
            assert isinstance(d.get("sentences", []), list)

    return call_with_retry(llm, prompt, schema, check)
