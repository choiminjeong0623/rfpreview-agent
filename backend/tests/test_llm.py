"""AI 호출 규칙: 재시도 횟수, 실패 메시지, 사실에 없는 숫자 버리기 (CR-07, CR-12)."""

import pytest

from rfp_agent.llm import tasks
from rfp_agent.llm.client import (
    CONFIG_FAILURE_MESSAGE,
    FAILURE_MESSAGE,
    MAX_RETRIES,
    LLMConfigError,
    LLMFailure,
    LLMFormatError,
    make_llm,
)
from rfp_agent.llm.evidence import EvidenceSpan
from tests.conftest import FakeLLM

DROPPED = tasks.DroppedExplanation(tasks.NUMBER_NOT_ALLOWED)


def test_no_key_means_no_llm():
    from rfp_agent.config import Settings
    assert make_llm(Settings(gemini_api_key=None, rfp_ai_mode="gemini")) is None


def test_retries_then_fails_with_message():
    llm = FakeLLM(fail=True)
    with pytest.raises(LLMFailure, match=FAILURE_MESSAGE):
        tasks.classify_document(llm, "a.docx", "first page")
    assert len(llm.prompts) == MAX_RETRIES + 1


FACTS = "파일 6 174행: 0.5 % 이내\n파일 6 278행: 1 % 이내"
SPANS = [EvidenceSpan("E-6-174", "Annual leakage rate shall be 0.5 % or less."),
         EvidenceSpan("E-6-278", "The leakage rate shall not exceed 1 % per year.")]


class ClaimLLM(FakeLLM):
    """정해 둔 설명 문장 하나를 낸다."""

    def __init__(self, text="허용 누설량이 두 곳에서 다르다.", quote="0.5 % or less",
                 ids=("E-6-174",)):
        super().__init__()
        self.claim = {"text": text, "exact_quote": quote, "evidence_ids": list(ids),
                      "relation": "DIRECT"}

    def generate_json(self, prompt, schema):
        self.prompts.append(prompt)
        return {"claims": [self.claim]}


def test_explanation_with_invented_number_is_dropped():
    llm = ClaimLLM(text="허용 누설량이 연간 2 % 로 더 크다.")
    assert tasks.explain_risk(llm, "VALUE_MISMATCH", FACTS, SPANS) == DROPPED


def test_explanation_keeps_claim_with_quote_and_evidence():
    """근거 조각 ID와 그 조각에 있는 인용을 댄 설명만 남는다 (add-claim-evidence)."""
    llm = ClaimLLM()
    out = tasks.explain_risk(llm, "VALUE_MISMATCH", FACTS, SPANS)
    assert isinstance(out, tasks.RiskExplanation) and out.text == "허용 누설량이 두 곳에서 다르다."
    assert out.claims[0].evidence_ids == ("E-6-174",) and out.claims[0].relation == "DIRECT"
    assert "[E-6-174] Annual leakage rate" in llm.prompts[0]


@pytest.mark.parametrize("quote, ids, reason", [
    ("2 % per year", ("E-6-174",), tasks.QUOTE_NOT_FOUND),      # 인용이 근거 조각에 없다
    ("1 % per year", ("E-6-174",), tasks.QUOTE_NOT_FOUND),      # 다른 조각 인용을 엉뚱한 ID로
    ("0.5 % or less", ("E-9-999",), tasks.UNKNOWN_EVIDENCE),    # 주지 않은 근거 ID
])
def test_explanation_with_unsupported_quote_is_dropped(quote, ids, reason):
    """Scenario: 근거에 없는 인용 — 인용·근거 ID가 맞지 않으면 설명을 버리고 이유를 남긴다."""
    llm = ClaimLLM(quote=quote, ids=ids)
    assert tasks.explain_risk(llm, "VALUE_MISMATCH", FACTS, SPANS) == tasks.DroppedExplanation(
        reason)


def test_number_from_other_span_is_dropped():
    """Scenario: 다른 근거 조각의 숫자 — 문장이 댄 조각에 없는 숫자는 버린다.

    1은 사실에도 있으므로, 사실 없이 근거 조각만으로 본다.
    """
    llm = ClaimLLM(text="이 조항의 누설량은 연간 1 % 이내다.")
    assert tasks.explain_risk(llm, "VALUE_MISMATCH", "누설량이 문서마다 다르다", SPANS) == DROPPED
    # 같은 숫자라도 그 숫자가 있는 조각을 대면 통과
    ok = ClaimLLM(text="이 조항의 누설량은 연간 1 % 이내다.", quote="1 % per year",
                  ids=("E-6-278",))
    assert isinstance(tasks.explain_risk(ok, "VALUE_MISMATCH", "누설량이 문서마다 다르다", SPANS),
                      tasks.RiskExplanation)


@pytest.mark.parametrize("text", ["허용 누설량이 다른 곳의 두 배다.", "허용 누설량이 절반이다.",
                                  "The leakage is twice the other value."])
def test_quantity_word_not_in_evidence_is_dropped(text):
    """Scenario: 근거에 없는 배수 말 — 숫자 없이 크기를 말해도 근거에 없으면 버린다."""
    assert tasks.explain_risk(ClaimLLM(text=text), "VALUE_MISMATCH", FACTS, SPANS) == DROPPED


def test_quantity_word_in_evidence_is_kept():
    spans = [EvidenceSpan("E-1-1", "The rating shall be twice the normal current.")]
    llm = ClaimLLM(text="정격이 평상 전류의 twice로 적혀 있다.", quote="twice the normal",
                   ids=("E-1-1",))
    assert isinstance(tasks.explain_risk(llm, "BLANKET", "정격 조건", spans),
                      tasks.RiskExplanation)


def test_explanation_failure_is_not_hidden():
    """Scenario: 설명을 받지 못함 — 정해진 횟수만 다시 묻고 실패를 알린다 (CR-12)."""
    llm = FakeLLM(fail=True)
    with pytest.raises(LLMFailure):
        tasks.explain_risk(llm, "VALUE_MISMATCH", FACTS, SPANS)
    assert len(llm.prompts) == MAX_RETRIES + 1


class ShortListLLM(FakeLLM):
    """긴 목록이면 답을 하나 빠뜨리는 모델. 같은 질문에는 늘 같은 답(temperature 0)."""

    def generate_json(self, prompt, schema):
        self.prompts.append(prompt)
        n = sum(1 for line in prompt.splitlines() if line[:1].isdigit() and ". " in line)
        return {"types": [{"n": i, "v": "TECH_PERF"} for i in range(n - 1 if n > 10 else n)]}


def test_missing_answer_splits_chunk_and_keeps_count():
    """모델이 40개 중 하나를 빠뜨려도 묶음을 나눠 다시 물어 개수를 맞춘다."""
    texts = [f"요구사항 {i}" for i in range(40)]
    out = tasks.type_unclassified(ShortListLLM(), texts)
    assert out == ["TECH_PERF"] * 40


class NumberedLLM(FakeLLM):
    """줄 번호를 붙인 답을 정해 둔 방식으로 흩뜨린다 (update-ai-answer-checks)."""

    def __init__(self, mode: str):
        super().__init__()
        self.mode = mode

    def generate_json(self, prompt, schema):
        self.prompts.append(prompt)
        lines = [line for line in prompt.splitlines() if line[:1].isdigit() and ". " in line]
        answer = [{"n": int(line.split(".")[0]), "v": "COST" if "비용" in line else "TECH_PERF"}
                  for line in lines]
        if self.mode == "reversed":
            answer.reverse()
        elif self.mode == "duplicate" and len(answer) > 1:
            answer[-1] = dict(answer[0])            # 마지막 번호를 빠뜨리고 0번을 두 번
        return {"types": answer}


def test_reversed_answers_are_put_back_in_order():
    """Scenario: 순서가 섞인 답 — 번호로 맞춰 바른 순서로 낸 답과 같다."""
    texts = ["비용 조건", "정격 전류", "정격 전압", "비용 부담"]
    expected = ["COST", "TECH_PERF", "TECH_PERF", "COST"]
    assert tasks.type_unclassified(NumberedLLM("reversed"), texts) == expected
    assert tasks.type_unclassified(NumberedLLM("in_order"), texts) == expected


def test_duplicate_number_is_rejected_and_split():
    """Scenario: 번호가 겹친 답 — 개수가 맞아도 받지 않고 다시 묻고, 나눠 물어 맞춘다."""
    texts = [("비용 " if i % 3 == 0 else "정격 ") + str(i) for i in range(40)]
    llm = NumberedLLM("duplicate")
    out = tasks.type_unclassified(llm, texts)
    assert out == ["COST" if i % 3 == 0 else "TECH_PERF" for i in range(40)]
    whole = [p for p in llm.prompts if p.count("\n") >= 40]
    assert len(whole) == 1                  # 40줄 묶음은 한 번만 묻고 바로 나눔 (B6)


class DraftLLM(FakeLLM):
    """문장 초안 줄마다 정해 둔 답을 낸다."""

    def __init__(self, texts):
        super().__init__()
        self.texts = texts

    def generate_json(self, prompt, schema):
        self.prompts.append(prompt)
        return {"texts": [{"n": n, "text": t} for n, t in enumerate(self.texts)]}


def test_draft_lines_must_use_every_placeholder():
    """자리표시자를 다 쓴 줄만 AI 문장, 나머지 줄은 None (부르는 곳이 코드 기본 문장으로)."""
    marks = {"v1": "요구값", "p": "제품"}
    llm = DraftLLM(["{p}는 {v1}을 맞춘다.", "{v1}만 썼다.", "{p} {v1} {x} 없는 자리표시자",
                    "{p}가 타사보다 {v1} 좋다.", " "])
    out = tasks.draft_sentences(llm, "시험", [("사실", marks)] * 5)
    assert out == ["{p}는 {v1}을 맞춘다.", None, None, None, None]
    assert len(llm.prompts) == 1                    # 줄 내용 때문에 다시 묻지 않는다


# ── 오류 종류별 처리 (update-llm-retry-kinds) ─────────────────────

class EmptyClaimsLLM(FakeLLM):
    def generate_json(self, prompt, schema):
        super().generate_json(prompt, schema)
        return {"claims": []}


def test_format_error_is_not_retried():
    """Scenario: 형식이 틀린 답은 다시 묻지 않음 · Scenario: 형식이 틀린 설명."""
    llm = EmptyClaimsLLM()
    out = tasks.explain_risk(llm, "VALUE_MISMATCH", FACTS, SPANS)
    assert out == tasks.DroppedExplanation(tasks.FORMAT_ERROR)
    assert len(llm.prompts) == 1 and llm.usage.calls == 1 and llm.usage.retries == 0


class NotJsonLLM(FakeLLM):
    def generate_json(self, prompt, schema):
        import json
        super().generate_json(prompt, schema)
        return json.loads("{잘린 답")


def test_not_json_is_format_error():
    llm = NotJsonLLM()
    with pytest.raises(LLMFormatError):
        tasks.classify_document(llm, "a.docx", "first page")
    assert len(llm.prompts) == 1


class KeyErrorLLM(FakeLLM):
    """google.genai ClientError처럼 code를 가진 오류."""

    def generate_json(self, prompt, schema):
        super().generate_json(prompt, schema)
        err = RuntimeError("401 API key not valid")
        err.code = 401
        raise err


def test_key_error_stops_at_once():
    """키 오류는 다시 묻지 않고 설정 오류로 바로 멈춘다."""
    llm = KeyErrorLLM()
    with pytest.raises(LLMConfigError, match=CONFIG_FAILURE_MESSAGE):
        tasks.label_sentences(llm, None, ["The breaker shall be provided."] * 40)
    assert len(llm.prompts) == 1                # 나눠 묻지도 않는다


def test_draft_chunk_with_bad_numbers_uses_code():
    """번호가 겹친 초안 묶음은 다시 묻지 않고 그 묶음 줄 모두 None."""
    class Dup(FakeLLM):
        def generate_json(self, prompt, schema):
            self.prompts.append(prompt)
            return {"texts": [{"n": 0, "text": "{v1}"}, {"n": 0, "text": "{v1}"}]}

    llm = Dup()
    assert tasks.draft_sentences(llm, "시험", [("사실", {"v1": "요구값"})] * 2) == [None, None]
    assert len(llm.prompts) == 1
