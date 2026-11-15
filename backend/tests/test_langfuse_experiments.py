"""평가셋을 Langfuse 데이터셋으로, 끝난 평가를 실험으로 (change add-langfuse-experiments).

명세 prompt-evaluation "평가셋을 Langfuse 데이터셋으로", "평가 결과를 Langfuse 실험으로"의
Scenario. 진짜 Langfuse 대신 같은 공개 API(데이터셋·항목·점수·프로젝트·OTLP)를 흉내 낸 가짜 서버.
"""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from rfp_agent.api.main import app
from rfp_agent.config import get_settings
from rfp_agent.db import cli
from rfp_agent.llm import client as llm_client
from rfp_agent.llm import prompt_source, tasks
from rfp_agent.pipeline import langfuse_ops, prompt_editor
from rfp_agent.pipeline import prompt_eval as pe
from tests.test_langfuse_prompts import EDITED, FakeLangfuse, fake_langfuse
from tests.test_prompt_eval import Scripted, answers_for, jsonl, type_item

HOST = "http://langfuse.local:3000"


class FakeLangfuseData(FakeLangfuse):
    """프롬프트·OTLP에 더해 데이터셋(v2)·데이터셋 항목(id로 덮어씀)·점수(배열)·프로젝트."""

    def __init__(self):
        super().__init__()
        self.datasets: dict[str, dict] = {}
        self.items: dict[str, dict] = {}
        self.scores: list[dict] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if self.down:
            return super().handler(request)
        if request.method == "GET" and path.startswith("/api/public/v2/datasets/"):
            self.requests.append(request)
            found = self.datasets.get(path.rsplit("/", 1)[1])
            return httpx.Response(200, json=found) if found else httpx.Response(404, json={})
        if request.method == "POST" and path == "/api/public/v2/datasets":
            self.requests.append(request)
            body = json.loads(request.content)
            ds = {"id": f"ds{len(self.datasets) + 1}", **body}
            self.datasets[body["name"]] = ds
            return httpx.Response(200, json=ds)
        if request.method == "POST" and path == "/api/public/dataset-items":
            self.requests.append(request)
            body = json.loads(request.content)
            assert body["datasetName"] in self.datasets
            self.items[body["id"]] = body
            return httpx.Response(200, json=body)
        if request.method == "POST" and path == "/api/public/scores":
            self.requests.append(request)
            body = json.loads(request.content)
            assert isinstance(body, list)
            self.scores += body
            return httpx.Response(200, json={})
        if request.method == "GET" and path == "/api/public/projects":
            self.requests.append(request)
            return httpx.Response(200, json={"data": [{"id": "proj1", "name": "rfp"}]})
        return super().handler(request)

    def spans(self) -> list[dict]:
        out = []
        for t in self.traces:
            for s in t["resourceSpans"][0]["scopeSpans"][0]["spans"]:
                out.append({**s, "attrs": {a["key"]: next(iter(a["value"].values()))
                                           for a in s["attributes"]}})
        return out


@pytest.fixture
def langfuse(monkeypatch):
    fake = FakeLangfuseData()
    monkeypatch.setattr("tests.test_langfuse_prompts.FakeLangfuse", lambda: fake)
    monkeypatch.setenv("RFP_LANGFUSE_RECORD", "on")
    yield from fake_langfuse(monkeypatch)
    get_settings.cache_clear()


def small_set(name: str = "small") -> pe.EvalSet:
    return pe.parse_set(name, jsonl([type_item(n) for n in range(4)]))


def test_push_dataset_twice(langfuse):
    """Scenario: 평가셋을 데이터셋으로 올리기 — 두 번 올려도 항목 수는 같다."""
    public = pe.load_set(pe.find_set("public", get_settings()))
    first = langfuse_ops.push_dataset(public, private=False)
    second = langfuse_ops.push_dataset(public, private=False)
    assert first.name == "rfp-eval-public" and first.items == len(public.items)
    assert len(langfuse.items) == len(public.items) and second.items == first.items
    assert len(langfuse.datasets) == 1
    assert first.url == f"{HOST}/project/proj1/datasets/ds1"
    item = langfuse.items[f"public-{public.items[0].id}"]
    assert item["input"] == public.items[0].input
    assert item["expectedOutput"] == public.items[0].expected
    assert item["metadata"]["role"] == public.items[0].role
    assert item["metadata"]["made_by"] == public.items[0].made_by


def test_private_set_refused(langfuse, monkeypatch, tmp_path):
    """Scenario: 비공개 평가셋은 올리지 않음 — 거절되고 Langfuse에 요청하지 않는다."""
    with pytest.raises(langfuse_ops.LangfuseError, match="외부로 보내지 않습니다"):
        langfuse_ops.push_dataset(small_set(), private=True)
    # 명령도 data/private 아래 평가셋이면 거절
    monkeypatch.setenv("PRIVATE_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    (tmp_path / "eval").mkdir()
    (tmp_path / "eval" / "secret.jsonl").write_text(jsonl([type_item(0)]), encoding="utf-8")
    with pytest.raises(SystemExit, match="외부로 보내지 않습니다"):
        cli.langfuse_command("langfuse-push-dataset", None, None, "secret")
    assert langfuse.requests == []


def _done(db, evalset: pe.EvalSet, repeat: int, wrong=frozenset(), fail_on=None):
    llm = Scripted(answers_for(evalset, wrong=wrong), fail_on=fail_on)
    result = pe.evaluate(evalset, llm, "GEMINI", repeat)
    pe.save(db, result)
    return result


def test_experiment_per_repeat(db, langfuse):
    """Scenario: 평가를 실험으로 기록.

    반복마다 실험 하나, 문항마다 항목에 이은 trace 하나, 맞음 1·틀림 0·답 없음은 점수 없음.
    """
    s = small_set()
    result = _done(db, s, 2, wrong={"t001"}, fail_on="Requirement line 3 ")
    url = langfuse_ops.record_experiment(result, prompt_source.code_set(), private=False)
    langfuse_ops.save_url(db, result.eval_id, url)
    spans = langfuse.spans()
    assert len(langfuse.traces) == 2 and len(spans) == 8
    exps = {s["attrs"]["langfuse.experiment.id"] for s in spans}
    assert exps == {f"eval-{result.eval_id}-r1", f"eval-{result.eval_id}-r2"}
    assert len({s["traceId"] for s in spans}) == 8                  # 문항마다 trace 하나
    for sp in spans:
        a = sp["attrs"]
        assert a["langfuse.experiment.item.root_observation_id"] == sp["spanId"]
        assert a["langfuse.experiment.item.id"] in langfuse.items
        assert a["langfuse.experiment.dataset.id"] == "ds1"
        assert "langfuse.observation.prompt.name" not in a          # 코드 판
    by_item = {(sc["traceId"]): sc["value"] for sc in langfuse.scores}
    item_of = {sp["traceId"]: sp["attrs"]["rfp.item_id"] for sp in spans}
    values = sorted((item_of[t], v) for t, v in by_item.items())
    assert values == [("t000", 1), ("t000", 1), ("t001", 0), ("t001", 0),
                      ("t002", 1), ("t002", 1)]                        # t003 답 없음은 점수 없음
    assert all(sc["name"] == "ok" and sc["dataType"] == "NUMERIC" for sc in langfuse.scores)
    row = pe.runs(db, "small")[0]
    assert row["langfuse_url"] == f"{HOST}/project/proj1/datasets/ds1"
    # 같은 평가를 다시 보내도 trace id는 같다
    first_ids = sorted(sp["traceId"] for sp in spans)
    langfuse.traces.clear()
    langfuse_ops.record_experiment(result, prompt_source.code_set(), private=False)
    assert sorted(sp["traceId"] for sp in langfuse.spans()) == first_ids


def test_langfuse_prompt_linked(db, langfuse):
    """Scenario: Langfuse 판 문항은 프롬프트 버전과 이음 — 유형 문항에만 rfp-type과 버전."""
    n = langfuse.add("type", EDITED, ["production"])
    prompts = prompt_source.resolve(fresh=True)
    public = pe.load_set(pe.find_set("public", get_settings()))
    draft = next(i for i in public.items if i.role == "draft")
    s = pe.parse_set("mix", jsonl([type_item(0), {
        "id": draft.id, "role": "draft", "made_by": draft.made_by, "input": draft.input,
        "expected": draft.expected}]))
    with prompt_source.use(prompts):
        result = _done(db, s, 1)
    langfuse_ops.record_experiment(result, prompts, private=False)
    attrs = {sp["attrs"]["rfp.role"]: sp["attrs"] for sp in langfuse.spans()}
    assert attrs["type"]["langfuse.observation.prompt.name"] == "rfp-type"
    assert attrs["type"]["langfuse.observation.prompt.version"] == str(n)
    assert attrs["type"]["rfp.prompt_version"] == f"{tasks.PROMPTS['type']}+lf{n}"
    assert "langfuse.observation.prompt.name" not in attrs["draft"]


def _cli(monkeypatch, db_url, tmp_path, evalset_lines):
    path = tmp_path / "small.jsonl"
    path.write_text(jsonl(evalset_lines), encoding="utf-8")
    s = pe.load_set(path)
    llm = Scripted(answers_for(s))
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    monkeypatch.setattr(llm_client, "make_llm", lambda settings: llm)
    monkeypatch.setattr(llm_client, "ai_mode", lambda settings: "GEMINI")
    return path


def test_record_off_sends_nothing(db, db_url, langfuse, monkeypatch, tmp_path, capsys):
    """Scenario: 끄면 실험을 보내지 않음 — 요청 없음, 평가 기록의 Langfuse 주소는 비어 있다."""
    monkeypatch.setenv("RFP_LANGFUSE", "off")
    monkeypatch.setenv("RFP_LANGFUSE_RECORD", "off")
    path = _cli(monkeypatch, db_url, tmp_path, [type_item(n) for n in range(3)])
    assert cli.eval_prompts(str(path), 1, False, True, None, False, None) == 0
    assert langfuse.requests == []
    row = pe.runs(db, "small")[0]
    assert row["status"] == "DONE" and row["langfuse_url"] is None
    assert "Langfuse 실험" not in capsys.readouterr().out


def test_cli_records_experiment(db, db_url, langfuse, monkeypatch, tmp_path, capsys):
    """eval-prompts가 끝난 평가를 실험으로 남기고 평가 기록에 주소를 둔다."""
    monkeypatch.setenv("RFP_LANGFUSE", "off")                # 코드 판으로 평가, 기록만 보냄
    path = _cli(monkeypatch, db_url, tmp_path, [type_item(n) for n in range(3)])
    assert cli.eval_prompts(str(path), 1, False, True, None, False, None) == 0
    assert len(langfuse.spans()) == 3 and len(langfuse.scores) == 3
    assert pe.runs(db, "small")[0]["langfuse_url"] == f"{HOST}/project/proj1/datasets/ds1"
    assert "[Langfuse 실험] 반복 1번을 실험으로 남김" in capsys.readouterr().out


def test_unreachable_keeps_eval(db, db_url, langfuse, monkeypatch, tmp_path, capsys):
    """Scenario: 실험을 보내지 못해도 평가는 남음 — 기록·보고서는 그대로, 주소는 비고 이유 출력."""
    monkeypatch.setenv("RFP_LANGFUSE", "off")
    path = _cli(monkeypatch, db_url, tmp_path, [type_item(n) for n in range(3)])
    langfuse.down = True
    assert cli.eval_prompts(str(path), 1, False, True, None, False, None) == 0
    out = capsys.readouterr().out
    assert "[Langfuse 실험] 보내지 못함: Langfuse 요청 실패" in out
    assert "유형" in out                                          # 보고서는 그대로
    row = pe.runs(db, "small")[0]
    assert row["status"] == "DONE" and row["langfuse_url"] is None


def test_prompt_view_shows_langfuse_link(db, db_url, langfuse, monkeypatch):
    """Scenario: 프롬프트 관리에서 Langfuse 실험 보기 — 판 기록 최근 평가·화면 평가 결과에 주소."""
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    prompt_editor._jobs.clear()
    public = pe.load_set(pe.find_set("public", get_settings()))
    monkeypatch.setattr(llm_client, "make_llm", lambda settings: Scripted(answers_for(public)))
    monkeypatch.setattr(llm_client, "ai_mode", lambda settings: "GEMINI")
    staged = langfuse.add("type", EDITED, ["staging"])
    eng = db.execute("SELECT min(user_id) FROM app_user WHERE role = 'ENGINEER'").fetchone()[0]
    prompt_editor.start_eval(db, "type", eng, wait=True)
    client = TestClient(app)
    job = client.get("/api/prompts/type/evaluations/latest").json()
    url = f"{HOST}/project/proj1/datasets/ds1"
    assert job["status"] == "DONE" and job["langfuse_url"] == url and job["langfuse_error"] is None
    spans = langfuse.spans()
    assert spans and {sp["attrs"]["rfp.role"] for sp in spans} == {"type"}
    assert len({sp["attrs"]["langfuse.experiment.id"] for sp in spans}) == 3   # 반복 3
    overview = client.get("/api/prompts").json()
    typ = next(r for r in overview["roles"] if r["role"] == "type")
    ver = next(v for v in typ["versions"] if v["version"] == f"{tasks.PROMPTS['type']}+lf{staged}")
    assert ver["eval"]["langfuse_url"] == url
    assert client.get("/api/health").json()["langfuse_record"] is True
    prompt_editor._jobs.clear()
