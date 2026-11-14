"""역할마다 고정 입력으로 만든 프롬프트 글과 그 해시 (add-prompt-eval, "판을 올리세요" 테스트).

역할 함수를 그대로 부르고, 모델에 보내려던 프롬프트·답 형식만 받아 적은 뒤 멈춘다.
해시가 바뀌면 그 역할의 프롬프트 글이 바뀐 것이다.

해시 파일 다시 만들기: `uv run python -m tests.prompt_samples > tests/fixtures/prompt_hashes.json`
"""

import hashlib
import json

from rfp_agent.llm import tasks
from rfp_agent.llm.client import LLMFailure
from rfp_agent.llm.evidence import EvidenceSpan


class _Stop(Exception):
    """첫 프롬프트를 받아 적은 뒤 멈춘다. 설정 오류 코드라 다시 묻지 않는다."""
    code = 400


class _Capture:
    model = "capture"
    workers = 1

    def __init__(self):
        self.sent: list[str] = []

    def generate_json(self, prompt: str, schema: dict) -> dict:
        self.sent.append(prompt + "\n" + json.dumps(schema, sort_keys=True, ensure_ascii=False))
        raise _Stop


def _first(call) -> str:
    llm = _Capture()
    try:
        call(llm)
    except LLMFailure:
        pass
    return llm.sent[0]


HINT = "요구 사양서"
SAMPLES = {
    "classify": [lambda m: tasks.classify_document(
        m, "sample.docx", "SECTION 1 GENERAL\nThe switchgear shall comply with IEC 62271.")],
    "label": [lambda m: tasks.label_sections(
        m, [("3. Tests", ["The contractor shall submit type test reports."])], doc_hint=HINT)],
    "type": [lambda m: tasks.type_unclassified(
        m, ["Type test reports shall be submitted."], contexts=["4.2 Tests"],
        examples=[[("Routine tests shall be witnessed.", "TEST")]], doc_hint=HINT)],
    "risk": [lambda m: tasks.explain_risk(
        m, "AMBIGUOUS_SCOPE", "범위: 포괄 표현",
        [EvidenceSpan("E-1-1", "including but not limited to all accessories")])],
    "verify": [lambda m: tasks.check_support(
        m, (tasks.Claim("범위가 넓다.", "but not limited to", ("E-1-1",), "DIRECT"),),
        {"E-1-1": "including but not limited to all accessories"})],
    "draft": [lambda m: tasks.draft_sentences(
        m, "일탈·질의 목록", [("항목: 정격 전류, 요구값 {v1} A", {"v1": "요구값(A)"})])],
    "handoff": [lambda m: tasks.department_questions(
        m, "COST", ["Liquidated damages shall apply for late delivery."])],
    "assistant": [lambda m: tasks.assistant_step(m, "시험 성적서를 요구하는 조항", "", True),
                  lambda m: tasks.assistant_step(
                      m, "시험 성적서를 요구하는 조항",
                      "[R1] 유형 TEST · Type test reports shall be submitted.", False)],
}


def role_prompts() -> dict[str, str]:
    return {role: "\n----\n".join(_first(c) for c in calls) for role, calls in SAMPLES.items()}


def role_hashes() -> dict[str, dict[str, str]]:
    return {role: {"version": tasks.PROMPTS[role],
                   "sha256": hashlib.sha256(text.encode()).hexdigest()[:16]}
            for role, text in role_prompts().items()}


if __name__ == "__main__":
    print(json.dumps(role_hashes(), ensure_ascii=False, indent=2))
