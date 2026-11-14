"""AI 묶음 동시 호출 (change update-llm-concurrency, NFR-10)."""

import re
import threading
import time
import zlib

import pytest

from rfp_agent.llm import tasks
from rfp_agent.llm.client import LLMFailure
from rfp_agent.llm.parallel import run_ordered
from rfp_agent.pipeline.run import RunContext, create_run, execute_run
from tests.conftest import FakeLLM
from tests.docx_factory import build_gis_spec

VERSION = "test-dict-v1"


def crc(text: str) -> int:
    return zlib.crc32(text.encode())


class EchoLLM(FakeLLM):
    """줄마다 다른 답을 내고, 묻는 글에 따라 늦게 답해 끝나는 순서를 섞는 대역.

    답이 줄 내용으로 정해지므로, 순서가 섞여 저장되면 결과가 달라진다.
    """

    def __init__(self, workers: int, model: str = "fake-model"):
        super().__init__()
        self.workers = workers
        self.model = model
        self.active = self.peak = 0
        self._lock = threading.Lock()

    def generate_json(self, prompt: str, schema: dict) -> dict:
        with self._lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
        try:
            time.sleep((crc(prompt) % 4) * 0.01)
            answer = super().generate_json(prompt, schema)
        finally:
            with self._lock:
                self.active -= 1
        lines = re.findall(r"^\d+\. (.*)$", prompt, re.MULTILINE)
        if "labels" in answer:
            answer["labels"] = [{"n": n, "v": ("REQUIREMENT", "DESCRIPTION")[crc(t) % 2]}
                                for n, t in enumerate(lines)]
        elif "types" in answer:
            answer["types"] = [{"n": n, "v": tasks.TYPE_CODES[crc(t) % len(tasks.TYPE_CODES)]}
                               for n, t in enumerate(lines)]
        elif "texts" in answer:
            answer["texts"] = [{"n": a["n"], "text": "초안 " + "abcdefghij"[crc(line) % 10] + " "
                                + a["text"]}
                               for line, a in zip(lines, answer["texts"], strict=True)]
        return answer


def run_with(db, paths, llm):
    run_id = create_run(db, VERSION, llm)
    stage = execute_run(RunContext(db, VERSION, llm, None), run_id, paths)
    assert stage == "ENGINEER_REVIEW", db.execute(
        "SELECT failed_step, error_message FROM review_run WHERE run_id = %s", (run_id,)).fetchone()
    return run_id


def snapshot(db, run_id):
    """요구사항 구분·유형, 위험 조건 설명, 일탈·질의·제안 포인트 문장 (ID 없이 순서대로)."""
    docs = [r[0] for r in db.execute(
        "SELECT document_id FROM run_document WHERE run_id = %s", (run_id,))]
    reqs = db.execute(
        """SELECT q.text_raw, q.req_kind, q.rule_id,
                  (SELECT string_agg(t.type_code, ',' ORDER BY t.type_code)
                     FROM requirement_type_tag t WHERE t.requirement_id = q.requirement_id)
           FROM requirement q WHERE q.document_id = ANY(%s) ORDER BY q.requirement_id""",
        (docs,)).fetchall()
    risks = db.execute("SELECT risk_kind, facts, explanation_ai FROM risk_flag WHERE run_id = %s "
                       "ORDER BY risk_id", (run_id,)).fetchall()
    outputs = db.execute("SELECT list_kind, text_draft FROM output_item WHERE run_id = %s "
                         "ORDER BY item_id", (run_id,)).fetchall()
    points = db.execute("SELECT point_kind, text_draft FROM proposal_point WHERE run_id = %s "
                        "ORDER BY point_id", (run_id,)).fetchall()
    return reqs, risks, outputs, points


def test_same_result_regardless_of_workers(db, spec, tmp_path, monkeypatch):
    """Scenario: 동시 개수와 상관없이 같은 결과.

    같은 문서를 동시 1개와 동시 4개로 처리하면 구분·유형·설명·초안과 요청 수·토큰이 같다.
    """
    # AI 묶음 동시 개수만 보려고 문서는 차례로 처리한다 (문서 병렬은 add-document-processors)
    from rfp_agent.config import get_settings
    from rfp_agent.pipeline import run as run_mod
    one_doc = get_settings().model_copy(update={"rfp_doc_workers": 1})
    monkeypatch.setattr(run_mod, "get_settings", lambda: one_doc)
    # 처리 키가 겹치면 두 번째 실행이 문서를 다시 쓰므로 모델 이름을 달리한다
    one, four = EchoLLM(1, "fake-a"), EchoLLM(4, "fake-b")
    gis = build_gis_spec(tmp_path / "synthetic_154kV_GIS_spec.docx")
    paths = [gis, spec]                # 문장·위험 조건이 있는 문서 + 판정 대상 데이터시트
    a, b = snapshot(db, run_with(db, paths, one)), snapshot(db, run_with(db, paths, four))
    assert a == b
    reqs, risks, outputs, points = a
    # AI 답이 실제로 반영됨: 설명으로 고른 문장은 빠지고, 유형은 줄마다 다르다
    assert len(reqs) < len(snapshot(db, run_with(db, paths, FakeLLM()))[0])
    assert any(r[3] and r[3] != "MAKER_QUAL" for r in reqs)
    assert risks and all(r[2] for r in risks)
    assert outputs and points
    assert one.peak == 1
    assert (one.usage.calls, one.usage.input_tokens) == (four.usage.calls, four.usage.input_tokens)
    assert one.usage.calls == len(one.prompts) == len(four.prompts)


def sections(count: int, size: int = tasks.CHUNK):
    return [(f"절 {n}", [f"문장 {n}-{i} shall be provided." for i in range(size)])
            for n in range(count)]


def test_batches_run_concurrently():
    """Scenario: 동시에 보냄.

    묶음이 여러 개면 같은 때 진행 중인 요청이 둘 이상이고 넷을 넘지 않는다.
    """
    llm = EchoLLM(4)
    out = tasks.label_sections(llm, sections(10))
    assert 2 <= llm.peak <= 4
    assert len(llm.prompts) == 10
    # 답은 절·줄 순서대로 (끝난 순서와 상관없음)
    for (_, texts), labels in zip(sections(10), out, strict=True):
        assert labels == [("REQUIREMENT", "DESCRIPTION")[crc(tasks.one_line(t)[:600]) % 2]
                          for t in texts]


def test_progress_grows_per_batch():
    """Scenario: 묶음마다 진행.

    끝난 줄 수는 묶음이 끝날 때마다 늘고 마지막 기록에서 전체 줄 수와 같다.
    """
    seen: list[tuple[int, int]] = []
    data = sections(3, 50)                  # 절마다 40 + 10줄 → 묶음 6개
    tasks.label_sections(EchoLLM(4), data, lambda done, total: seen.append((done, total)))
    assert len(seen) == 6
    dones = [d for d, _ in seen]
    assert dones == sorted(dones) and len(set(dones)) == 6
    assert seen[-1] == (150, 150)


class BadLLM(EchoLLM):
    """"BAD"가 든 묶음은 언제나 실패한다."""

    def generate_json(self, prompt: str, schema: dict) -> dict:
        if "BAD" in prompt:
            self.prompts.append(prompt)
            time.sleep(0.01)
            raise TimeoutError("응답 시간 초과")
        return super().generate_json(prompt, schema)


def test_failing_batch_stops_the_rest(db, spec):
    """Scenario: 한 묶음이 계속 실패.

    재시도 뒤에도 실패한 묶음이 있으면 남은 묶음은 보내지 않고, 실행은 FAILED가 된다.
    """
    data = [("절", ["BAD shall be provided."])] + sections(20)[1:]
    llm = BadLLM(2)
    with pytest.raises(LLMFailure):
        tasks.label_sections(llm, data)
    asked = {m.group(1) for p in llm.prompts for m in re.finditer(r"절 제목: (.*)", p)}
    assert len(asked) < 20                  # 끝까지 보내지 않았다

    failing = FakeLLM(fail=True)
    failing.workers = 4
    run_id = create_run(db, VERSION, failing)
    assert execute_run(RunContext(db, VERSION, failing, None), run_id, [spec]) == "FAILED"


def test_cancel_during_concurrent_batches():
    """Scenario: 동시 호출 중 취소.

    진행 알림(취소 확인)이 멈추라고 하면 멈추고, 보낸 요청 수는 전체 묶음 수보다 적다.
    """
    class Cancelled(Exception):
        pass

    def report(done: int, total: int) -> None:
        raise Cancelled("취소")

    llm = EchoLLM(2)
    with pytest.raises(Cancelled):
        tasks.label_sections(llm, sections(20), report)
    assert len(llm.prompts) < 20


def test_on_done_runs_in_caller_thread():
    """진행 알림(DB 쓰기)은 부르는 스레드에서만 한다."""
    me = threading.get_ident()
    where = []
    out = run_ordered([lambda i=i: (time.sleep(0.01 * (5 - i)), i)[1] for i in range(5)], 3,
                      lambda i, r: where.append(threading.get_ident()))
    assert out == [0, 1, 2, 3, 4]
    assert set(where) == {me}


def test_request_timeout_is_set(monkeypatch):
    """Scenario: 응답이 늦은 요청.

    클라이언트를 만들면 요청 시간 제한이 설정값(초)으로 걸린다. 시간 초과는 다시 시도된다.
    """
    import google.genai

    from rfp_agent.config import get_settings
    from rfp_agent.llm.client import MAX_RETRIES, make_llm

    made = {}

    class Client:
        def __init__(self, **kwargs):
            made.update(kwargs)

    monkeypatch.setattr(google.genai, "Client", Client)
    s = get_settings().model_copy(update={"gemini_api_key": "key", "rfp_ai_mode": "gemini"})
    llm = make_llm(s)
    assert made["http_options"] == {"timeout": 120_000}
    assert (llm.workers, llm.timeout_s) == (4, 120)

    slow = FakeLLM(fail=True)               # 매번 TimeoutError
    with pytest.raises(LLMFailure):
        tasks.label_sentences(slow, None, ["The breaker shall be provided."])
    assert slow.usage.calls == MAX_RETRIES + 1 and slow.usage.retries == MAX_RETRIES
