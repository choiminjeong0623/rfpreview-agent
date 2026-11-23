"""프롬프트 품질 평가 (change add-prompt-eval, 명세 prompt-evaluation, FR-18·NFR-13).

평가셋(JSONL) 문항을 llm/tasks.py의 역할 함수에 그대로 묻고(답 검사도 그대로 거침),
코드로만 채점한다(CR-01). 전체 처리 흐름은 돌리지 않는다. AI 채점자는 쓰지 않는다.

평가셋 줄 모양 (역할마다 input·expected가 다름, data/eval/README.md):
  {"id", "role", "made_by": HUMAN|CODE|CLAUDE_DRAFT, "input", "expected", "injection_of"?}
첫 줄이 {"meta": {"threshold_pp": 2}}이면 평가셋 설정이다.
"""

import hashlib
import json
import logging
import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from rfp_agent.llm import tasks
from rfp_agent.llm.client import LLM, LLMFailure, LLMFormatError, usage_of
from rfp_agent.llm.evidence import EvidenceSpan
from rfp_agent.llm.parallel import run_ordered, workers_of
from rfp_agent.pipeline import code_version
from rfp_agent.pipeline.numbers import fill
from rfp_agent.pipeline.req_eval import normalize, same_line
from rfp_agent.pipeline.run_log import USD_KRW, estimated_cost_krw

ROLES = ("label", "type", "draft", "assistant", "risk", "verify")
SOURCES = ("HUMAN", "CODE", "CLAUDE_DRAFT")          # 지표를 보이는 순서: 사람 기준이 먼저
SOURCE_NAMES = {"HUMAN": "사람", "CODE": "코드", "CLAUDE_DRAFT": "Claude 초안"}
WEAK = "근거 약함"                                   # Claude 초안 정답만으로 낸 지표
DEFAULT_THRESHOLD_PP = 2.0
ANSWER_TOKENS = 200                                  # 비용 어림: 답 하나의 토큰 (design 4장)
NO_AI = "AI 없음: 평가하지 않음"
ROLE_NAMES = {"label": "문장 구분", "type": "유형", "draft": "문장 초안",
              "assistant": "검토 도우미", "risk": "위험 설명", "verify": "검증"}
# 지표 이름과 좋은 쪽 (up: 높을수록 좋음).
# 비율이 아닌 지표(평균 도구 호출 수)는 회귀 판정에 쓰지 않음
METRICS = {
    "label": [("recall", "요구사항 재현율", "up"), ("precision", "요구사항 정확도", "up"),
              ("accuracy", "구분 일치율", "up")],
    "type": [("accuracy", "유형 정확도", "up")],
    "draft": [("pass_rate", "검사 통과율", "up")],
    "assistant": [("tool_accuracy", "도구 선택 정확도", "up"),
                  ("evidence_recall", "근거 줄 재현율", "up"),
                  ("ref_pass_rate", "근거 번호 통과율", "up"),
                  ("no_answer_rate", "답하지 못한 비율", "down"),
                  ("avg_tool_calls", "평균 도구 호출 수", None)],
    "risk": [("agreement", "사람 표시 일치율", "up")],
    "verify": [("agreement", "사람 표시 일치율", "up")],
}


class EvalError(Exception):
    """평가를 시작할 수 없음 (평가셋 없음, 상한 초과 등)."""


# ── 평가셋 ─────────────────────────────────────────────────────────────

@dataclass
class Item:
    id: str
    role: str
    made_by: str
    input: dict
    expected: dict
    line_no: int
    injection_of: str | None = None


@dataclass
class EvalSet:
    name: str
    version: str                                     # 파일 내용 sha256 앞 12자
    items: list[Item]
    errors: list[str] = field(default_factory=list)  # 형식이 틀려 뺀 줄 ("3번 줄: …")
    threshold_pp: float = DEFAULT_THRESHOLD_PP

    def by_role(self) -> dict[str, int]:
        """역할별 문항 수 (주입 문항 제외 — 주입 문항은 주입 영향으로만 센다)."""
        return {r: n for r in ROLES
                if (n := sum(i.role == r and not i.injection_of for i in self.items))}

    def by_source(self) -> dict[str, int]:
        return {s: n for s in SOURCES if (n := sum(i.made_by == s for i in self.items))}

    def injections(self) -> list[Item]:
        return [i for i in self.items if i.injection_of]


def _is_text(x) -> bool:
    return isinstance(x, str) and bool(x.strip())


def _check_shape(role: str, inp: dict, exp: dict) -> str | None:
    """역할별 입력·정답 모양. 틀리면 이유 한 마디."""
    if role == "label":
        sents, labels = inp.get("sentences"), exp.get("labels")
        if not isinstance(sents, list) or not sents or not all(_is_text(s) for s in sents):
            return "input.sentences(문장 목록)가 필요합니다"
        if not isinstance(labels, list) or len(labels) != len(sents):
            return "expected.labels가 문장 수와 같아야 합니다"
        if any(x not in tasks.SENTENCE_LABELS for x in labels):
            return "expected.labels에 모르는 구분이 있습니다"
    elif role == "type":
        if not _is_text(inp.get("text")):
            return "input.text가 필요합니다"
        if exp.get("type") not in tasks.TYPE_CODES:
            return "expected.type이 유형 코드가 아닙니다"
    elif role == "draft":
        marks, values = inp.get("marks"), inp.get("values")
        if not _is_text(inp.get("facts")) or not isinstance(marks, dict) or not marks:
            return "input.facts와 input.marks(자리표시자)가 필요합니다"
        if not isinstance(values, dict) or set(values) != set(marks):
            return "input.values가 자리표시자마다 있어야 합니다"
        if not isinstance(exp.get("usable"), bool):
            return "expected.usable(참·거짓)이 필요합니다"
    elif role == "assistant":
        if not _is_text(inp.get("question")) or not _is_text(inp.get("fixture")):
            return "input.question과 input.fixture가 필요합니다"
        if exp.get("first_tool") not in tasks.ASSISTANT_ACTIONS:
            return "expected.first_tool이 도구 이름이 아닙니다"
        if not isinstance(exp.get("evidence_texts", []), list):
            return "expected.evidence_texts는 목록입니다"
    elif role == "risk":
        spans = inp.get("spans")
        if not _is_text(inp.get("kind")) or not isinstance(spans, list) or not spans:
            return "input.kind와 input.spans(근거 조각)가 필요합니다"
        if not all(isinstance(s, dict) and _is_text(s.get("id")) and _is_text(s.get("text"))
                   for s in spans):
            return "input.spans 줄마다 id·text가 필요합니다"
        if not isinstance(exp.get("acceptable"), bool):
            return "expected.acceptable(사람 표시: 참·거짓)이 필요합니다"
    elif role == "verify":
        claims, verdicts = inp.get("claims"), exp.get("verdicts")
        if not isinstance(claims, list) or not claims or not isinstance(inp.get("sources"), dict):
            return "input.claims와 input.sources가 필요합니다"
        if not isinstance(verdicts, list) or len(verdicts) != len(claims) \
                or any(v not in tasks.VERDICTS for v in verdicts):
            return "expected.verdicts가 문장마다 YES·NO·UNSURE여야 합니다"
    return None


def parse_set(name: str, text: str) -> EvalSet:
    """JSONL 글을 읽는다. 형식이 틀린 줄은 빼고 줄 번호를 errors에 남긴다."""
    version = hashlib.sha256(text.encode()).hexdigest()[:12]
    out = EvalSet(name, version, [])
    seen: set[str] = set()
    for no, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            out.errors.append(f"{no}번 줄: JSON이 아닙니다")
            continue
        if not isinstance(row, dict):
            out.errors.append(f"{no}번 줄: 객체가 아닙니다")
            continue
        if "meta" in row:
            meta = row["meta"] if isinstance(row["meta"], dict) else {}
            if isinstance(meta.get("threshold_pp"), int | float):
                out.threshold_pp = float(meta["threshold_pp"])
            continue
        missing = [k for k in ("id", "role", "made_by", "input", "expected") if k not in row]
        if missing:
            out.errors.append(f"{no}번 줄: {', '.join(missing)} 칸이 없습니다")
            continue
        if row["role"] not in ROLES:
            out.errors.append(f"{no}번 줄: 모르는 역할 {row['role']}")
            continue
        if row["made_by"] not in SOURCES:
            out.errors.append(f"{no}번 줄: made_by는 HUMAN·CODE·CLAUDE_DRAFT 중 하나입니다")
            continue
        if not isinstance(row["input"], dict) or not isinstance(row["expected"], dict):
            out.errors.append(f"{no}번 줄: input·expected는 객체입니다")
            continue
        if (why := _check_shape(row["role"], row["input"], row["expected"])) is not None:
            out.errors.append(f"{no}번 줄: {why}")
            continue
        if row["id"] in seen:
            out.errors.append(f"{no}번 줄: 문항 번호 {row['id']}가 겹칩니다")
            continue
        seen.add(row["id"])
        out.items.append(Item(str(row["id"]), row["role"], row["made_by"], row["input"],
                              row["expected"], no, row.get("injection_of")))
    ids = {i.id: i for i in out.items}
    for i in list(out.items):
        base = ids.get(i.injection_of) if i.injection_of else None
        if i.injection_of and (base is None or base.role != i.role):
            out.errors.append(f"{i.line_no}번 줄: injection_of {i.injection_of}에 같은 역할 짝이 "
                              "없습니다")
            out.items.remove(i)
    return out


def load_set(path: Path, name: str | None = None) -> EvalSet:
    if not path.exists():
        raise EvalError(f"평가셋 파일이 없습니다: {path}")
    return parse_set(name or path.stem, path.read_text(encoding="utf-8"))


def find_set(name: str, settings) -> Path:
    """이름 또는 경로. 이름이면 공개(data/eval) → 비공개(data/private/eval) 순서로 찾는다."""
    p = Path(name)
    if p.suffix == ".jsonl":
        return p
    for base in (settings.seed_dir.parent / "eval", settings.private_data_dir / "eval"):
        if (base / f"{name}.jsonl").exists():
            return base / f"{name}.jsonl"
    raise EvalError(f"평가셋을 찾지 못했습니다: {name} (data/eval 또는 data/private/eval)")


# ── 문항 하나 묻기 ──────────────────────────────────────────────────────

@dataclass
class Answer:
    ok: bool | None                  # None = 답 없음
    answer: dict | None = None
    error: str | None = None         # FORMAT / FAILED / CONFIG / BUDGET(비용 상한으로 묻지 않음)
    signature: str | None = None     # 주입 짝 비교용 결과 요약
    counts: dict = field(default_factory=dict)   # 지표 재료 {지표: (num, den)}
    ms: int | None = None            # 묻는 데 걸린 시간(재시도·도구 반복 포함, add-model-compare)


def _error_kind(exc: Exception) -> str:
    if isinstance(exc, LLMFormatError):
        return "FORMAT"
    return "FAILED"


@dataclass
class Fixture:
    """검토 도우미 문항이 찾을 검토 (평가 전용 스키마). 이름 → (연결, 검토 번호)."""
    runs: dict[str, tuple[psycopg.Connection, int]] = field(default_factory=dict)


def _label(llm: LLM, item: Item) -> Answer:
    got = tasks.label_sentences(llm, item.input.get("section"), item.input["sentences"])
    exp = item.expected["labels"]
    tp = sum(g == e == "REQUIREMENT" for g, e in zip(got, exp, strict=True))
    return Answer(got == exp, {"labels": got}, signature=json.dumps(got), counts={
        "recall": (tp, exp.count("REQUIREMENT")), "precision": (tp, got.count("REQUIREMENT")),
        "accuracy": (sum(g == e for g, e in zip(got, exp, strict=True)), len(exp))})


def _type(llm: LLM, item: Item) -> Answer:
    got = tasks.type_unclassified(llm, [item.input["text"]],
                                  contexts=[item.input.get("context")])[0]
    ok = got == item.expected["type"]
    return Answer(ok, {"type": got}, signature=got, counts={"accuracy": (int(ok), 1)})


def _draft(llm: LLM, item: Item) -> Answer:
    marks, values = item.input["marks"], item.input["values"]
    text = tasks.draft_sentences(llm, item.input.get("purpose", "일탈·질의 목록"),
                                 [(item.input["facts"], marks)])[0]
    # 받아들임 = 자리표시자 모두 사용·경쟁 비교 없음(역할 함수 검사) + 채운 숫자가 근거와 맞음
    usable = text is not None and fill(text, values).check == "OK"
    ok = usable == item.expected["usable"]
    return Answer(ok, {"text": text, "usable": usable}, signature=str(usable),
                  counts={"pass_rate": (int(usable), 1)})


def _risk(llm: LLM, item: Item) -> Answer:
    spans = [EvidenceSpan(s["id"], s["text"]) for s in item.input["spans"]]
    out = tasks.explain_risk(llm, item.input["kind"], item.input.get("facts", ""), spans)
    if isinstance(out, tasks.DroppedExplanation) and out.reason == tasks.FORMAT_ERROR:
        return Answer(None, {"dropped": out.reason}, error="FORMAT", counts=no_answer_counts(item))
    accepted = isinstance(out, tasks.RiskExplanation)
    ok = accepted == item.expected["acceptable"]
    answer = {"text": out.text} if accepted else {"dropped": out.reason}
    return Answer(ok, answer, signature=str(accepted), counts={"agreement": (int(ok), 1)})


def _verify(llm: LLM, item: Item) -> Answer:
    claims = tuple(tasks.Claim(c["text"], c.get("quote", ""), tuple(c.get("evidence_ids", [])),
                               c.get("relation", "DIRECT")) for c in item.input["claims"])
    got = tasks.check_support(llm, claims, item.input["sources"])
    exp = item.expected["verdicts"]
    same = sum(g == e for g, e in zip(got, exp, strict=True))
    return Answer(same == len(exp), {"verdicts": got}, signature=json.dumps(got),
                  counts={"agreement": (same, len(exp))})


def _assistant(llm: LLM, item: Item, fixture: Fixture) -> Answer:
    from rfp_agent.pipeline.assistant import ask

    name = item.input["fixture"]
    if name not in fixture.runs:
        return Answer(None, error=f"FIXTURE: {name} 없음")
    conn, run_id = fixture.runs[name]
    out = ask(conn, run_id, item.input["question"], llm)
    exp = item.expected
    expected_texts = [normalize(t) for t in exp.get("evidence_texts", [])]
    if out["mode"] != "AI":                          # AI가 답하지 못해 글자로 찾음
        return Answer(None, {"note": out["note"]}, error="FAILED", counts=no_answer_counts(item))
    steps = out["steps"]
    first = steps[0]["tool"] if steps else "answer"
    tool_ok = first == exp["first_tool"] and (
        not exp.get("type_code") or (steps and steps[0].get("type_code") == exp["type_code"]))
    got_texts = [normalize(e["text_raw"]) for e in out["evidence"]]
    hit = sum(any(same_line(t, g) for g in got_texts) for t in expected_texts)
    kept = len(out["sentences"])
    answer = {"steps": steps, "sentences": out["sentences"],
              "evidence": [e["text_raw"] for e in out["evidence"]], "dropped": out["dropped"]}
    return Answer(bool(tool_ok and hit == len(expected_texts) and kept), answer,
                  signature=json.dumps(sorted(got_texts)),
                  counts={"tool_accuracy": (int(bool(tool_ok)), 1),
                          "evidence_recall": (hit, len(expected_texts)),
                          "no_answer_rate": (int(kept == 0), 1),
                          "ref_pass_rate": (kept, kept + out["dropped"]),
                          "avg_tool_calls": (len(steps), 1)})


RUNNERS: dict[str, Callable[[LLM, Item], Answer]] = {
    "label": _label, "type": _type, "draft": _draft, "risk": _risk, "verify": _verify}


def ask_item(llm: LLM, item: Item, fixture: Fixture | None = None) -> Answer:
    """문항 하나. 호출이 재시도 뒤에도 실패하면 '답 없음'(ok None)으로 센다."""
    try:
        if item.role == "assistant":
            return _assistant(llm, item, fixture or Fixture())
        return RUNNERS[item.role](llm, item)
    except LLMFailure as exc:
        return Answer(None, error=_error_kind(exc), counts=no_answer_counts(item))


def timed_ask(llm: LLM, item: Item, fixture: Fixture | None = None) -> Answer:
    """문항 하나를 묻고 걸린 시간(밀리초)을 적는다. 답 없음도 기다린 시간은 같으므로 적는다."""
    started = time.monotonic()
    answer = ask_item(llm, item, fixture)
    answer.ms = round((time.monotonic() - started) * 1000)
    return answer


def nearest_rank(values: list[int], pct: float) -> int | None:
    """최근접 순위 백분위수: 정렬한 값의 ceil(p/100 × n)번째. 값이 없으면 None."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(1, math.ceil(pct / 100 * len(ordered))) - 1]


def no_answer_counts(item: Item) -> dict:
    """답 없음 문항이 지표에 더하는 것: 분모에는 들어가고 맞힌 수에는 들어가지 않는다."""
    exp = item.expected
    if item.role == "label":
        n = len(exp["labels"])
        return {"recall": (0, exp["labels"].count("REQUIREMENT")), "precision": (0, 0),
                "accuracy": (0, n)}
    if item.role == "verify":
        return {"agreement": (0, len(exp["verdicts"]))}
    if item.role == "assistant":
        return {"tool_accuracy": (0, 1), "evidence_recall": (0, len(exp.get("evidence_texts", []))),
                "no_answer_rate": (1, 1), "ref_pass_rate": (0, 0), "avg_tool_calls": (0, 0)}
    return {m: (0, 1) for m, _, _ in METRICS[item.role]}


# ── 검토 도우미 평가용 검토 (평가 전용 스키마) ─────────────────────────────

FIXTURE_SCHEMA = "prompt_eval_fixture"
FIXTURE_SOURCES = {"synthetic_rfp28": "synthetic_rfp28_type.csv"}   # 이름 → 정답지 CSV(합성 문서)
FIXTURE_DICT_VERSION = "prompt-eval-fixture"


def fixture_docx(csv_path: Path, out: Path) -> Path:
    """합성 RFP 정답지 줄로 docx를 만든다: 문맥(절·표 이름)마다 제목, 표 줄(" / ")은 표 행."""
    import csv

    from docx import Document

    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    doc = Document()
    doc.add_paragraph("REQUEST FOR PROPOSAL — SYNTHETIC EVALUATION FIXTURE")
    context, table = None, None
    for row in rows:
        text, ctx = row["text"].strip(), (row.get("context") or "").strip()
        if ctx != context:
            context, table = ctx, None
            if ctx:
                doc.add_paragraph(ctx)
        cells = [c.strip() for c in text.split(" / ")]
        if len(cells) >= 3:
            if table is None:
                table = doc.add_table(rows=1, cols=len(cells))
                for cell, name in zip(table.rows[0].cells,
                                      ["No.", "Item", "Unit", "Required", "Offered"], strict=False):
                    cell.text = name
            row_cells = table.add_row().cells
            for cell, value in zip(row_cells, cells, strict=False):
                cell.text = value
        else:
            table = None
            doc.add_paragraph(text)
    doc.save(str(out))
    return out


def _fixture_version(csv_path: Path, settings) -> str:
    digest = hashlib.sha256(csv_path.read_bytes())
    digest.update(code_version().encode())
    for p in sorted(settings.migrations_dir.glob("*.sql")):
        digest.update(p.name.encode())
    return digest.hexdigest()[:12]


def open_fixtures(names: set[str], settings, workdir: Path, url: str | None = None) -> Fixture:
    """도우미 문항이 찾을 검토를 평가 전용 스키마에 만든다(규칙만, AI 없음). 판이 같으면 다시 쓴다.

    개발 DB의 public 스키마는 건드리지 않는다.
    """
    from langgraph.checkpoint.memory import InMemorySaver

    from rfp_agent.db.migrate import migrate
    from rfp_agent.db.seed import seed_rules
    from rfp_agent.pipeline.run import RunContext, create_run, execute_run

    fixture = Fixture()
    for name in sorted(names):
        if name not in FIXTURE_SOURCES:
            raise EvalError(f"모르는 도우미 평가 검토: {name} ({', '.join(FIXTURE_SOURCES)})")
        csv_path = settings.seed_dir / "answer_keys" / FIXTURE_SOURCES[name]
        version = _fixture_version(csv_path, settings)
        schema = f"{FIXTURE_SCHEMA}_{name}"
        conn = psycopg.connect(url or settings.database_url,
                               options=f"-c search_path={schema}")
        conn.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        conn.commit()
        found = None
        if conn.execute("SELECT to_regclass('review_run')").fetchone()[0] is not None:
            found = conn.execute(
                "SELECT run_id FROM review_run WHERE graph_state->>'fixture' = %s "
                "AND stage = 'ENGINEER_REVIEW' ORDER BY run_id DESC LIMIT 1",
                (version,)).fetchone()
        if found is None:
            conn.execute(f"DROP SCHEMA {schema} CASCADE")
            conn.execute(f"CREATE SCHEMA {schema}")
            conn.commit()
            migrate(conn, settings.migrations_dir)
            seed_rules(conn, settings.seed_dir)
            conn.commit()
            path = fixture_docx(csv_path, workdir / f"{name}.docx")
            run_id = create_run(conn, FIXTURE_DICT_VERSION, None)
            stage = execute_run(RunContext(conn, FIXTURE_DICT_VERSION, None, None,
                                           checkpointer=InMemorySaver()), run_id, [path])
            if stage != "ENGINEER_REVIEW":
                raise EvalError(f"도우미 평가 검토를 만들지 못했습니다: {name} ({stage})")
            conn.execute("UPDATE review_run SET graph_state = graph_state || %s "
                         "WHERE run_id = %s", (Jsonb({"fixture": version}), run_id))
            conn.commit()
            found = (run_id,)
        fixture.runs[name] = (conn, found[0])
    return fixture


def close_fixtures(fixture: Fixture) -> None:
    for conn, _ in fixture.runs.values():
        conn.close()


# ── 채점 ───────────────────────────────────────────────────────────────

def _pct(num: int, den: int) -> float | None:
    return round(100 * num / den, 1) if den else None


def _role_metrics(items: list[Item], answers: list[Answer]) -> dict:
    """반복 한 번의 역할별 지표: {역할: {지표: {by_source: {출처: {num, den, value}}}}}.

    주입 문항은 역할 지표에 넣지 않는다(짝 문항과 비교해 주입 영향으로만 센다).
    """
    out: dict = {}
    for role in ROLES:
        pairs = [(i, a) for i, a in zip(items, answers, strict=True)
                 if i.role == role and not i.injection_of]
        if not pairs:
            continue
        role_out: dict = {}
        for metric, _, better in METRICS[role]:
            by_source = {}
            for src in SOURCES:
                got = [a.counts.get(metric, (0, 0)) for i, a in pairs if i.made_by == src]
                if not got:
                    continue
                num, den = sum(n for n, _ in got), sum(d for _, d in got)
                # 평균 도구 호출 수만 비율이 아닌 평균. 분모가 0이면 값 없음
                value = (round(num / den, 2) if den else None) if metric == "avg_tool_calls" \
                    else _pct(num, den)
                by_source[src] = {"num": num, "den": den, "value": value}
                if better:
                    # 회귀를 문항(질문) 단위로 세는 재료: 이 지표가 모자란 문항 수,
                    # 지표가 있는 문항 수.
                    # 근거 번호처럼 한 문항에 분모가 여럿인 지표도 문항 하나로 센다
                    by_source[src]["short"] = sum(
                        1 for n, d in got if d and (n < d if better == "up" else n > 0))
                    by_source[src]["questions"] = sum(1 for _, d in got if d)
            role_out[metric] = {"by_source": by_source}
        n = len(pairs)
        fmt = sum(a.error == "FORMAT" for _, a in pairs)
        none = sum(a.ok is None for _, a in pairs)
        role_out["format_error_rate"] = {"by_source": {"ALL": {
            "num": fmt, "den": n, "value": _pct(fmt, n)}}}
        role_out["no_answer"] = {"by_source": {"ALL": {"num": none, "den": n,
                                                       "value": _pct(none, n)}}}
        out[role] = role_out
    return out


def basis_of(by_source: dict) -> str | None:
    """지표의 기준 출처: 사람 → 코드 → Claude 초안 중 분모가 있는 첫 출처."""
    for src in (*SOURCES, "ALL"):
        if by_source.get(src, {}).get("den"):
            return src
    return None


def merge_repeats(per_repeat: list[dict]) -> dict:
    """반복마다의 지표를 합친다: 출처별 값은 첫 반복, 기준 출처 값의 최소·최대·평균."""
    merged: dict = {}
    for role, metrics in per_repeat[0].items():
        merged[role] = {}
        for metric, first in metrics.items():
            basis = basis_of(first["by_source"])
            cells = [r[role][metric]["by_source"].get(basis, {}) for r in per_repeat]
            values = [c.get("value") for c in cells if c.get("value") is not None]
            # 최솟값을 낸 반복의 모자란 문항 수: 회귀를 문항 단위로 셀 때 쓴다
            low = min((c for c in cells if c.get("value") is not None),
                      key=lambda c: c["value"], default={})
            merged[role][metric] = {
                "by_source": first["by_source"], "basis": basis,
                "weak": basis == "CLAUDE_DRAFT",
                "min": min(values) if values else None, "max": max(values) if values else None,
                "min_short": low.get("short"), "questions": low.get("questions"),
                "mean": round(sum(values) / len(values), 2) if values else None,
                "repeats": [r[role][metric]["by_source"].get(basis, {}).get("value")
                            for r in per_repeat],
            }
    return merged


def injection_effects(items: list[Item], repeats: list[list[Answer]]) -> list[str]:
    """주입 문항 중 같은 반복에서 짝(지시문 없는 판)은 맞았는데 주입 판은 틀렸거나 답이 없는 문항.

    짝도 틀린 반복은 모델이 흔들린 것이라 주입 영향으로 세지 않는다 (11-15 측정, design 참고).
    """
    index = {i.id: n for n, i in enumerate(items)}
    hit = []
    for n, item in enumerate(items):
        if not item.injection_of:
            continue
        base = index[item.injection_of]
        if any(ans[base].ok is True and ans[n].ok is not True for ans in repeats):
            hit.append(item.id)
    return hit


# ── 비용 어림 ──────────────────────────────────────────────────────────

class _Capture:
    """프롬프트 글만 받아 적고 멈추는 모델 대역 (비용 어림용)."""
    model = "capture"
    workers = 1

    def __init__(self):
        self.chars = 0

    def generate_json(self, prompt: str, schema: dict) -> dict:
        self.chars += len(prompt) + len(json.dumps(schema))
        raise _Stop


class _Stop(Exception):
    code = 400                                       # 설정 오류로 보여 다시 묻지 않는다


def prompt_chars(item: Item) -> int:
    """문항 하나가 보낼 프롬프트 글자 수. 도우미는 첫 질문 글자 × 최대 질문 수."""
    from rfp_agent.pipeline.assistant import MAX_SEARCHES

    cap = _Capture()
    client_log = logging.getLogger("rfp_agent.llm.client")
    level = client_log.level
    client_log.setLevel(logging.ERROR)                  # 어림용 대역의 "설정 오류" 경고는 숨김
    try:
        if item.role == "assistant":
            tasks.assistant_step(cap, item.input["question"], "", True)
        else:
            RUNNERS[item.role](cap, item)
    except LLMFailure:
        pass
    finally:
        client_log.setLevel(level)
    calls = MAX_SEARCHES + 1 if item.role == "assistant" else 1
    return cap.chars * calls


def estimate(items: list[Item], repeat: int, model: str | None) -> dict:
    """(글자 ÷ 4 + 답 200토큰) × 반복 × 단가(실행 기록과 같은 팀 가정 단가표)."""
    from rfp_agent.pipeline.assistant import MAX_SEARCHES

    calls = sum(MAX_SEARCHES + 1 if i.role == "assistant" else 1 for i in items) * repeat
    input_tokens = sum(prompt_chars(i) for i in items) // 4 * repeat
    output_tokens = ANSWER_TOKENS * calls
    cost = estimated_cost_krw(model, input_tokens, output_tokens, 0)
    return {"calls": calls, "input_tokens": input_tokens, "output_tokens": output_tokens,
            "cost_krw": cost, "usd_krw": USD_KRW}


# ── 평가 실행 ──────────────────────────────────────────────────────────

@dataclass
class EvalResult:
    status: str                                      # DONE / SKIPPED
    set: EvalSet
    model: str | None
    ai_mode: str
    repeat: int
    metrics: dict = field(default_factory=dict)
    injection_hits: list[str] = field(default_factory=list)
    answers: list[list[Answer]] = field(default_factory=list)   # 반복마다 문항 순서대로
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    cost_krw: int | None = 0
    seconds: float = 0.0
    skip_reason: str | None = None
    estimate: dict | None = None
    eval_id: int | None = None
    provider: str | None = None                      # 모델 비교 (add-model-compare)
    compare_id: int | None = None
    latency_p50_ms: int | None = None
    latency_p95_ms: int | None = None

    @property
    def label(self) -> str:
        return f"{self.provider}:{self.model}" if self.provider else (self.model or "—")

    def format_error_rate(self) -> float | None:
        """모든 반복·문항 중 형식 오류로 버린 답의 비율(%)."""
        all_answers = [a for rep in self.answers for a in rep]
        return _pct(sum(a.error == "FORMAT" for a in all_answers), len(all_answers)) \
            if all_answers else None

    def item_ok(self) -> dict[str, bool | None]:
        """문항마다 모든 반복에서 맞았는가 (반복 중 하나라도 틀리면 틀림, 답 없음이면 None)."""
        out: dict[str, bool | None] = {}
        for n, item in enumerate(self.set.items):
            oks = [rep[n].ok for rep in self.answers]
            out[item.id] = None if any(o is None for o in oks) else all(oks)
        return out


def evaluate(evalset: EvalSet, llm: LLM | None, ai_mode: str, repeat: int = 1,
             max_krw: int = 500, confirmed: bool = False,
             fixture: Fixture | None = None) -> EvalResult:
    """평가셋을 repeat번 돌려 채점한다. AI 없음이면 건너뜀, 어림 비용이 상한을 넘으면 EvalError.

    문항은 동시에 묻고(llm/parallel) 결과는 문항 순서대로 모은다(CR-11).
    """
    model = getattr(llm, "model", None) if llm else None
    result = EvalResult("SKIPPED", evalset, model, ai_mode, repeat)
    if llm is None or ai_mode == "OFF":
        result.skip_reason = NO_AI
        return result
    if not evalset.items:
        raise EvalError("채점할 문항이 없습니다")
    est = estimate(evalset.items, repeat, model)
    result.estimate = est
    if est["cost_krw"] is not None and est["cost_krw"] > max_krw and not confirmed:
        raise EvalError(f"어림 비용 {est['cost_krw']:,}원이 상한 {max_krw:,}원을 넘습니다 "
                        f"(호출 {est['calls']}번, 입력 약 {est['input_tokens']:,}토큰, "
                        "팀 가정 단가). "
                        "그래도 하려면 --yes를 주세요.")
    usage = usage_of(llm)
    before = usage.copy() if usage else None
    # 실행 중 비용 상한 (add-ops-metrics): 확인 없으면 상한, 확인했으면 상한과 어림 두 배 중 큰 값
    stop_at = max_krw if not confirmed or est["cost_krw"] is None \
        else max(max_krw, est["cost_krw"] * 2)
    unasked = 0

    def spent() -> int | None:
        return _spent_krw(model, usage, before)

    def guarded(item: Item) -> Answer:
        nonlocal unasked
        cost = spent()
        if cost is not None and cost > stop_at:
            unasked += 1
            return Answer(None, error="BUDGET", counts=no_answer_counts(item))
        return timed_ask(llm, item, fixture)

    started = time.monotonic()
    per_repeat = []
    for n in range(repeat):
        cost = spent()
        if cost is not None and cost > stop_at:
            unasked += len(evalset.items) * (repeat - n)                 # 남은 반복은 통째로
            break
        jobs = [lambda item=item: guarded(item) for item in evalset.items]
        answers = run_ordered(jobs, workers_of(llm))
        result.answers.append(answers)
        per_repeat.append(_role_metrics(evalset.items, answers))
    result.seconds = round(time.monotonic() - started, 1)
    times = [a.ms for rep in result.answers for a in rep if a.ms is not None]
    result.latency_p50_ms, result.latency_p95_ms = nearest_rank(times, 50), nearest_rank(times, 95)
    result.metrics = merge_repeats(per_repeat)
    result.injection_hits = injection_effects(evalset.items, result.answers)
    if usage and before:
        d = usage.minus(before)
        result.calls, result.input_tokens = d.calls, d.input_tokens
        result.output_tokens, result.thinking_tokens = d.output_tokens, d.thinking_tokens
        result.cost_krw = estimated_cost_krw(model, d.input_tokens, d.output_tokens,
                                             d.thinking_tokens)
    if unasked:
        result.status = "FAILED"
        result.skip_reason = (f"비용 상한 {stop_at:,}원을 넘어 멈췄습니다 "
                              f"(쓴 비용 약 {spent():,}원, 묻지 않은 문항 {unasked}개, "
                              "팀 가정 단가)")
        return result
    result.status = "DONE"
    return result


def _spent_krw(model: str | None, usage, before) -> int | None:
    """지금까지 쓴 비용(팀 가정 단가). 사용량을 세지 않거나 단가를 모르면 None (상한 적용 안 함)."""
    if not usage or not before:
        return None
    d = usage.minus(before)
    return estimated_cost_krw(model, d.input_tokens, d.output_tokens, d.thinking_tokens)


# ── 기준선 비교 ────────────────────────────────────────────────────────

BASELINE_MIN_REPEAT = 3   # 기준선은 3번 이상 반복한 실행으로만 (최솟값끼리 비교)

@dataclass
class Comparison:
    has_baseline: bool
    regression: bool = False
    reasons: list[str] = field(default_factory=list)
    flipped: list[str] = field(default_factory=list)  # 기준선에서 맞았는데 이번에 틀린 문항
    note: str | None = None                           # "기준선 없음", "기준선 다시 만들기 필요"


def summary(result: EvalResult) -> dict:
    """기준선 파일·DB 기준선 비교에 쓰는 요약: 지표마다 기준 출처의 최솟값, 문항별 맞음."""
    return {"set_name": result.set.name, "set_version": result.set.version,
            "model": result.model, "repeat": result.repeat,
            "prompt_versions": tasks.prompt_versions(),
            "metrics": {role: {m: {"basis": v["basis"], "value": v["min"],
                                   "den": v["by_source"].get(v["basis"], {}).get("den"),
                                   "short": v.get("min_short"), "questions": v.get("questions")}
                               for m, v in ms.items()} for role, ms in result.metrics.items()},
            "items": result.item_ok()}


def compare(result: EvalResult, baseline: dict | None) -> Comparison:
    """회귀: 기준 지표 최솟값이 허용 문항 수보다 많이 떨어짐(`_dropped`) / 형식 오류율 오름 /
    주입 영향 ≥ 1."""
    cmp = Comparison(baseline is not None)
    if result.injection_hits:
        cmp.regression = True
        cmp.reasons.append(f"주입 영향 {len(result.injection_hits)}건: "
                           + ", ".join(result.injection_hits))
    if baseline is None:
        cmp.note = "기준선 없음"
        return cmp
    if baseline.get("set_version") != result.set.version:
        cmp.note = "기준선 다시 만들기 필요 (평가셋 판이 다름)"
        return cmp
    limit = result.set.threshold_pp
    for role, metrics in result.metrics.items():
        for metric, cur in metrics.items():
            old = baseline.get("metrics", {}).get(role, {}).get(metric)
            if not old or old.get("value") is None or cur["min"] is None:
                continue
            name = f"{ROLE_NAMES[role]} {_metric_name(role, metric)}"
            if metric == "format_error_rate":
                if cur["min"] > old["value"]:
                    cmp.regression = True
                    cmp.reasons.append(f"{name} {old['value']} → {cur['min']} %")
                continue
            better = dict((m, b) for m, _, b in METRICS[role]).get(metric)
            if better is None:
                continue
            drop = old["value"] - cur["min"] if better == "up" else cur["min"] - old["value"]
            if old.get("short") is not None and cur.get("min_short") is not None \
                    and cur.get("questions"):
                hit, detail = _lost_items(drop, cur["min_short"] - old["short"],
                                          cur["questions"], limit)
            else:                                    # 문항별 재료가 없는 예전 기준선
                hit, detail = _dropped(drop, cur["by_source"].get(cur["basis"], {}).get("den"),
                                       limit)
            if hit:
                cmp.regression = True
                cmp.reasons.append(f"{name} {old['value']} → {cur['min']} % ({detail})")
    now = result.item_ok()
    cmp.flipped = [i for i, ok in baseline.get("items", {}).items() if ok and now.get(i) is not True
                   and i in now]
    return cmp


def _lost_items(drop: float, lost: int, questions: int, limit: float) -> tuple[bool, str]:
    """지표가 떨어졌고, 지표가 모자란 문항이 허용 문항 수(문턱 %p × 문항 수 / 100과 1 가운데
    큰 값)보다 많이 늘었으면 회귀 (update-eval-threshold-items).

    도우미 8문항처럼 문항이 적은 역할은 한 문항이 문턱 %p보다 커서 3번 중 한 번의 흔들림도 회귀가
    되던 것, 근거 번호처럼 한 문항의 문장 여럿이 빠지면 여러 문항처럼 세던 것을 막는다.
    """
    lost = max(0, lost)
    allowed = max(1.0, limit * questions / 100)
    return drop > 0 and lost > allowed, (f"{lost}문항 떨어짐(허용 {allowed:g}문항, "
                                         f"문턱 {limit:g} %p, 문항 {questions})")


def _dropped(drop: float, den: int | None, limit: float) -> tuple[bool, str]:
    """문항별 재료(short)가 없는 예전 기준선용: 분모로 어림한 떨어진 수가 허용 수
    (문턱 %p × 분모 / 100과 1 가운데 큰 값)보다 많으면 회귀. 값이 0.1 단위로 반올림돼 있어 수도
    반올림한다. 분모를 모르면 문턱 %p로 본다.
    """
    if not den:
        return drop > limit, f"문턱 {limit:g} %p"
    lost = round(drop * den / 100, 1)
    allowed = max(1.0, limit * den / 100)
    return lost > allowed, (f"{lost:g}문항 떨어짐(허용 {allowed:g}문항, "
                            f"문턱 {limit:g} %p, 문항 {den})")


def _metric_name(role: str, metric: str) -> str:
    extra = {"format_error_rate": "형식 오류율", "no_answer": "답 없음"}
    return dict((m, n) for m, n, _ in METRICS[role]).get(metric) or extra.get(metric, metric)


# ── 저장 ──────────────────────────────────────────────────────────────

def save(conn: psycopg.Connection, result: EvalResult, baseline: bool = False,
         note: str | None = None, run_by: str | None = None) -> int:
    """평가 기록과 문항별 결과. baseline이면 같은 평가셋의 이전 기준선을 풀고 이번을 기준선으로."""
    with conn.transaction():
        if baseline and result.status == "DONE":       # 멈춘 평가는 예전 기준선을 풀지 않음
            conn.execute("UPDATE prompt_eval_run SET is_baseline = FALSE "
                         "WHERE set_name = %s AND is_baseline", (result.set.name,))
        eval_id = conn.execute(
            """INSERT INTO prompt_eval_run (set_name, set_version, model, ai_mode, prompt_versions,
                   code_version, repeat, status, skip_reason, metrics, injection_effect, calls,
                   input_tokens, output_tokens, cost_krw, seconds, is_baseline, note, run_by,
                   provider, compare_id, latency_p50_ms, latency_p95_ms)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                       %s, %s, %s, %s)
               RETURNING eval_id""",
            (result.set.name, result.set.version, result.model, result.ai_mode,
             Jsonb(tasks.prompt_versions()), code_version(), result.repeat, result.status,
             result.skip_reason, Jsonb(result.metrics), len(result.injection_hits), result.calls,
             result.input_tokens, result.output_tokens + result.thinking_tokens, result.cost_krw,
             result.seconds, baseline and result.status == "DONE", note, run_by,
             result.provider, result.compare_id, result.latency_p50_ms,
             result.latency_p95_ms)).fetchone()[0]
        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO prompt_eval_item (eval_id, repeat_no, item_id, role, made_by, ok,
                       answer, error) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                [(eval_id, r, item.id, item.role, item.made_by, a.ok,
                  Jsonb(a.answer) if a.answer is not None else None, a.error)
                 for r, answers in enumerate(result.answers, start=1)
                 for item, a in zip(result.set.items, answers, strict=True)])
    result.eval_id = eval_id
    return eval_id


def db_baseline(conn: psycopg.Connection, set_name: str) -> dict | None:
    """DB의 기준선 실행을 summary 모양으로."""
    with conn.cursor(row_factory=dict_row) as cur:
        run = cur.execute("SELECT * FROM prompt_eval_run WHERE set_name = %s AND is_baseline",
                          (set_name,)).fetchone()
        if run is None:
            return None
        items = cur.execute(
            """SELECT item_id, bool_and(ok) AS ok, bool_or(ok IS NULL) AS none
                 FROM prompt_eval_item WHERE eval_id = %s GROUP BY item_id""",
            (run["eval_id"],)).fetchall()
    return {"eval_id": run["eval_id"], "set_name": set_name, "set_version": run["set_version"],
            "model": run["model"], "prompt_versions": run["prompt_versions"],
            "metrics": {role: {m: {"basis": v.get("basis"), "value": v.get("min"),
                                   "den": v["by_source"].get(v.get("basis"), {}).get("den")}
                               for m, v in ms.items()} for role, ms in run["metrics"].items()},
            "items": {r["item_id"]: (None if r["none"] else r["ok"]) for r in items}}


def runs(conn: psycopg.Connection, set_name: str | None = None, limit: int = 100,
         eval_id: int | None = None) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            """SELECT eval_id, set_name, set_version, model, ai_mode, prompt_versions, code_version,
                      repeat, status, skip_reason, metrics, injection_effect, calls, input_tokens,
                      output_tokens, cost_krw, seconds, is_baseline, note, run_by, created_at,
                      provider, compare_id, latency_p50_ms, latency_p95_ms, langfuse_url
                 FROM prompt_eval_run
                WHERE (%(set)s::text IS NULL OR set_name = %(set)s)
                  AND (%(id)s::int IS NULL OR eval_id = %(id)s)
                ORDER BY eval_id DESC LIMIT %(limit)s""",
            {"set": set_name, "limit": limit, "id": eval_id}).fetchall()


def latest_by_model(rows: list[dict]) -> list[dict]:
    """평가셋별 보기: 모델마다 가장 최근 끝난 평가 (모델 비교, NFR-07)."""
    seen: dict[tuple, dict] = {}
    for r in rows:                                    # 최신순
        if r["status"] == "DONE":
            seen.setdefault((r["set_name"], r["model"]), r)
    return list(seen.values())


def items_of(conn: psycopg.Connection, eval_id: int) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            """SELECT repeat_no, item_id, role, made_by, ok, answer, error
                 FROM prompt_eval_item WHERE eval_id = %s ORDER BY repeat_no, item_id""",
            (eval_id,)).fetchall()


# ── 보고서 ─────────────────────────────────────────────────────────────

def _fmt(v) -> str:
    return "—" if v is None else f"{v:g}"


def report(result: EvalResult, cmp: Comparison | None) -> str:
    """마크다운 보고서 (표준 출력, CI 작업 요약)."""
    s = result.set
    head = [f"## 프롬프트 평가: {s.name}",
            "",
            f"- 평가셋 판 `{s.version}` · 문항 {len(s.items)}개 ("
            + ", ".join(f"{ROLE_NAMES[r]} {n}" for r, n in s.by_role().items())
            + (f", 주입 시험 {len(s.injections())}쌍" if s.injections() else "") + ")",
            "- 정답 만든 이: " + ", ".join(f"{SOURCE_NAMES[k]} {n}"
                                           for k, n in s.by_source().items())]
    if s.errors:
        head.append(f"- 형식이 틀려 뺀 줄 {len(s.errors)}개: " + "; ".join(s.errors[:10]))
    if result.status == "SKIPPED":
        return "\n".join([*head, "", f"**{result.skip_reason}**", ""])
    head += [f"- 모델 `{result.model}` ({result.ai_mode}) · 반복 {result.repeat}번 · "
             f"{result.seconds:g}초 · 호출 {result.calls}번 · 토큰 입력 {result.input_tokens:,} / "
             f"출력 {result.output_tokens + result.thinking_tokens:,} · 추정 비용 "
             + (f"{result.cost_krw:,}원 (팀 가정)" if result.cost_krw is not None
                else "단가 모름"),
             "- 프롬프트 판: " + " · ".join(f"{k} {v}" for k, v in tasks.prompt_versions().items()),
             f"- 주입 영향: {len(result.injection_hits)}건"
             + (" (" + ", ".join(result.injection_hits) + ")" if result.injection_hits else ""),
             "",
             f"| 역할 | 지표 | 기준 | 값(최소) | 최대 | 사람 | 코드 | Claude 초안({WEAK}) |",
             "|---|---|---|---:|---:|---:|---:|---:|"]
    if result.status == "FAILED" and result.skip_reason:
        head.insert(len(head) - 3, f"- **멈춤**: {result.skip_reason}. 아래 값은 멈추기 전 답만 "
                                   "센 것이라 기준선과 비교하지 않습니다")
    rows = []
    for role, metrics in result.metrics.items():
        for metric, v in metrics.items():
            def cell(src, v=v):
                x = v["by_source"].get(src)
                return f"{_fmt(x['value'])} ({x['num']}/{x['den']})" if x else "—"
            basis = SOURCE_NAMES.get(v["basis"], "전체") + (f" · {WEAK}" if v["weak"] else "")
            rows.append(f"| {ROLE_NAMES[role]} | {_metric_name(role, metric)} | {basis} | "
                        f"{_fmt(v['min'])} | {_fmt(v['max'])} | {cell('HUMAN')} | {cell('CODE')} | "
                        f"{cell('CLAUDE_DRAFT')} |")
    tail = [""]
    if cmp is not None:
        if cmp.note:
            tail.append(f"- 비교: {cmp.note}")
        tail.append("- **회귀**: " + "; ".join(cmp.reasons) if cmp.regression
                    else "- 회귀 없음")
        if cmp.flipped:
            tail.append(f"- 맞음 → 틀림 {len(cmp.flipped)}개: " + ", ".join(cmp.flipped))
    return "\n".join([*head, *rows, *tail, ""])


# ── 여러 회사 모델 비교 (add-model-compare, FR-23) ─────────────────────────

@dataclass
class ModelComparison:
    results: list[EvalResult]                         # --models 순서대로 (건너뜀 포함)
    cheapest: EvalResult | None = None
    cheapest_note: str = ""                           # 고른 이유 또는 고를 수 없는 이유
    unknown_price: list[str] = field(default_factory=list)
    compare_id: int | None = None


def is_private_set(path: Path, settings) -> bool:
    """고객 원문이 들 수 있는 평가셋(data/private 아래)."""
    try:
        path.resolve().relative_to(settings.private_data_dir.resolve())
    except ValueError:
        return False
    return True


def compare_models(evalset: EvalSet, specs: list, settings, repeat: int = 1,
                   max_krw: int = 500, confirmed: bool = False, private_set: bool = False,
                   fixture: Fixture | None = None, make=None) -> ModelComparison:
    """같은 평가셋·같은 프롬프트 판을 모델마다 평가한다. 상한은 보낼 수 있는 모델의 어림 비용 합.

    키가 없거나 외부 전송이 허용되지 않은 모델은 요청 없이 건너뜀으로 남긴다.
    """
    from rfp_agent.llm.client import make_compare_llm

    make = make or make_compare_llm
    if not evalset.items:
        raise EvalError("채점할 문항이 없습니다")
    plan: list[tuple] = []
    for spec in specs:
        llm, reason = make(spec, settings, private_set)
        plan.append((spec, llm, reason))
    out = ModelComparison([])
    total = 0
    for spec, llm, _ in plan:
        if llm is None:
            continue
        cost = estimate(evalset.items, repeat, spec.model)["cost_krw"]
        if cost is None:
            out.unknown_price.append(spec.label)
        else:
            total += cost
    if total > max_krw and not confirmed:
        skipped = f", 단가 모름 {len(out.unknown_price)}개 제외" if out.unknown_price else ""
        raise EvalError(f"모델 합계 어림 비용 {total:,}원이 상한 {max_krw:,}원을 넘습니다 "
                        f"(팀 가정 단가{skipped}). 그래도 하려면 --yes를 주세요.")
    for spec, llm, reason in plan:
        if llm is None:
            result = EvalResult("SKIPPED", evalset, spec.model, spec.provider.upper(), repeat,
                                skip_reason=reason)
        else:
            result = evaluate(evalset, llm, spec.provider.upper(), repeat, max_krw, True, fixture)
        result.provider = spec.provider
        out.results.append(result)
    out.cheapest, out.cheapest_note = cheapest(out.results, evalset.threshold_pp)
    return out


def primary_metric(role: str) -> str:
    """역할의 주 지표: METRICS의 첫 지표 (모두 높을수록 좋음)."""
    return METRICS[role][0][0]


def cheapest(results: list[EvalResult], threshold_pp: float) -> tuple[EvalResult | None, str]:
    """같은 품질에 가장 싼 모델 (CR-01, 코드만).

    역할마다 주 지표 최솟값이 그 역할의 최고 모델보다 문턱 넘게 낮지 않고, 주입 영향 0이며,
    추정 비용을 아는 모델 중 비용이 가장 적은 모델. 같으면 p95가 작은 쪽, 다음 이름순.
    """
    done = [r for r in results if r.status == "DONE"]
    if not done:
        return None, "고를 수 없음: 평가를 끝낸 모델이 없습니다"
    best: dict[str, float] = {}
    for r in done:
        for role in r.metrics:
            v = r.metrics[role].get(primary_metric(role), {}).get("min")
            if v is not None:
                best[role] = max(best.get(role, v), v)

    def within(r: EvalResult) -> bool:
        for role, top in best.items():
            v = r.metrics.get(role, {}).get(primary_metric(role), {}).get("min")
            if v is None or v < top - threshold_pp:
                return False
        return True

    good = [r for r in done if within(r) and not r.injection_hits]
    priced = [r for r in good if r.cost_krw is not None]
    if not priced:
        why = ("품질 문턱 안에 드는 모델의 단가를 모릅니다" if good
               else "품질 문턱 안에 들고 주입 영향이 없는 모델이 없습니다")
        return None, f"고를 수 없음: {why}"
    pick = min(priced, key=lambda r: (r.cost_krw, r.latency_p95_ms
                                      if r.latency_p95_ms is not None else math.inf, r.label))
    return pick, (f"{pick.label} — 역할마다 주 지표가 최고 모델과 {threshold_pp:g} %p 안, "
                  f"주입 영향 0, 추정 비용 {pick.cost_krw:,}원(팀 가정)")


def compare_report(evalset: EvalSet, cmp: ModelComparison) -> str:
    """모델 비교 마크다운 표 (표준 출력)."""
    roles = [r for r in ROLES if r in evalset.by_role()]
    head = [f"## 모델 비교: {evalset.name}", "",
            f"- 평가셋 판 `{evalset.version}` · 문항 {len(evalset.items)}개 · 반복 "
            f"{cmp.results[0].repeat if cmp.results else 1}번 · 문턱 {evalset.threshold_pp:g} %p"
            + (f" · 비교 묶음 {cmp.compare_id}" if cmp.compare_id else ""),
            "- 프롬프트 판: " + " · ".join(f"{k} {v}" for k, v in tasks.prompt_versions().items()),
            "- 주 지표는 정답 기준 출처(사람 → 코드 → Claude 초안)의 반복 최솟값(%)",
            ""]
    names = [(ROLE_NAMES[r], _metric_name(r, primary_metric(r))) for r in roles]
    cols = [m if role in m else f"{role} {m}" for role, m in names]   # "유형 유형 정확도" 피함
    head.append("| 모델 | 상태 | " + " | ".join(cols)
                + " | 형식 오류율 | 주입 영향 | 호출 | 토큰 입력/출력 | 추정 비용 | p50 | p95 |")
    head.append("|---|---|" + "---:|" * len(cols) + "---:|---:|---:|---:|---:|---:|---:|")
    rows = []
    for r in cmp.results:
        if r.status != "DONE":
            rows.append(f"| {r.label} | {r.skip_reason or r.status} |" + " — |" * (len(cols) + 7))
            continue
        vals = [_fmt(r.metrics.get(role, {}).get(primary_metric(role), {}).get("min"))
                for role in roles]
        cost = f"{r.cost_krw:,}원" if r.cost_krw is not None else "단가 모름"
        ms = lambda v: "—" if v is None else f"{v:,}ms"            # noqa: E731
        rows.append(f"| {r.label} | 끝남 | " + " | ".join(vals)
                    + f" | {_fmt(r.format_error_rate())} % | {len(r.injection_hits)} | {r.calls} | "
                      f"{r.input_tokens:,}/{r.output_tokens + r.thinking_tokens:,} | {cost} | "
                      f"{ms(r.latency_p50_ms)} | {ms(r.latency_p95_ms)} |")
    tail = ["", f"- **같은 품질에 가장 싼 모델**: {cmp.cheapest_note}"]
    if cmp.unknown_price:
        tail.append("- 단가 모름(비용 상한 합에서 뺌, `RFP_EVAL_PRICES`로 줄 수 있음): "
                    + ", ".join(cmp.unknown_price))
    tail.append("- 비용은 팀 가정 단가로 어림한 값이며 실제 청구 금액이 아님")
    return "\n".join([*head, *rows, *tail, ""])


def save_comparison(conn: psycopg.Connection, cmp: ModelComparison,
                    run_by: str | None = None) -> int:
    """비교 묶음 번호를 하나 받아 모델마다 평가 기록을 저장한다(기준선은 만들지 않음)."""
    compare_id = conn.execute("SELECT nextval('prompt_eval_compare_seq')").fetchone()[0]
    for r in cmp.results:
        r.compare_id = compare_id
        save(conn, r, baseline=False, note="모델 비교", run_by=run_by)
    cmp.compare_id = compare_id
    return compare_id


# ── 기존 정답지 → 평가셋 ────────────────────────────────────────────────

def export_type_key(conn: psycopg.Connection, key_name: str, out: Path) -> int:
    """유형 정답지(answer_key, TYPE)를 유형 평가셋 JSONL로 쓴다. 사람 확인 줄만 HUMAN.

    코드가 만든 정답(AUTO)은 CODE, 나머지는 CLAUDE_DRAFT. 쓴 줄 수를 돌려준다.
    """
    row = conn.execute("SELECT key_id, made_by, key_kind FROM answer_key WHERE key_name = %s",
                       (key_name,)).fetchone()
    if row is None:
        raise LookupError(f"정답지가 없습니다: {key_name}")
    key_id, made_by, kind = row
    if kind != "TYPE":
        raise LookupError(f"유형 정답지만 평가셋으로 바꿉니다: {key_name} ({kind})")
    rows = conn.execute(
        """SELECT row_no, text_raw, context, expected, human_checked, ambiguous
             FROM answer_key_row WHERE key_id = %s ORDER BY row_no""", (key_id,)).fetchall()
    slug = hashlib.sha256(key_name.encode()).hexdigest()[:6]
    lines = []
    for no, text, context, expected, human, ambiguous in rows:
        src = "HUMAN" if human else ("CODE" if made_by == "AUTO" else "CLAUDE_DRAFT")
        line = {"id": f"type-{slug}-{no:03d}", "role": "type", "made_by": src,
                "input": {"text": text, "context": context}, "expected": {"type": expected}}
        if ambiguous:
            line["note"] = "애매함"
        lines.append(json.dumps(line, ensure_ascii=False))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(lines)
