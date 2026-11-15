"""Langfuse에 프롬프트를 올리고, 평가를 통과한 판만 운영 표시로 옮기고, 호출 기록을 보낸다
(add-langfuse-prompts, ADR-010). 평가셋을 데이터셋으로, 끝난 평가를 실험으로 남긴다
(add-langfuse-experiments). 사람이 돌리는 명령(rfp-db)과 프롬프트 관리 화면 평가에서 부른다.
"""

import hashlib
import json
import time
from dataclasses import dataclass

import httpx
import psycopg

from rfp_agent.config import get_settings
from rfp_agent.llm import prompt_source, tasks
from rfp_agent.pipeline import ai_calls

PRODUCTION = "production"


class LangfuseError(Exception):
    """설정이 없거나 Langfuse가 거절했다. 사람에게 그대로 보인다."""


def _client() -> prompt_source.Client:
    lf = prompt_source.client()
    if lf is None:
        raise LangfuseError("LANGFUSE_HOST·LANGFUSE_PUBLIC_KEY·LANGFUSE_SECRET_KEY를 설정하세요.")
    return lf


@dataclass
class Pushed:
    role: str
    name: str
    version: int | None
    status: str                 # NEW(새 버전) | SAME(같은 글이 이미 그 표시에 있음)


def push_prompts(label: str) -> list[Pushed]:
    """코드 틀을 역할마다 Langfuse 새 버전으로 올리고 label을 붙인다.

    그 표시에 같은 글·같은 코드 판이 이미 있으면 올리지 않는다. 판 설정(config)에 코드 판을 적어
    두어, 코드 판이 바뀐 뒤에는 예전 틀이 쓰이지 않게 한다(prompt_source.check).
    """
    lf = _client()
    out = []
    try:
        for role, code_version in tasks.PROMPTS.items():
            name = prompt_source.name_of(role)
            text = tasks.TEMPLATES[role]
            now = lf.get_prompt(name, label)
            if now and now.get("prompt") == text \
                    and (now.get("config") or {}).get("code_version") == code_version:
                out.append(Pushed(role, name, now.get("version"), "SAME"))
                continue
            made = lf.create_prompt(name, text, [label], {"code_version": code_version},
                                    f"코드 판 {code_version}에서 올림")
            out.append(Pushed(role, name, made.get("version"), "NEW"))
    except (httpx.TransportError, httpx.HTTPStatusError) as exc:
        raise LangfuseError(f"Langfuse 요청 실패: {exc}") from exc
    prompt_source.clear_cache()
    return out


def promotable(prompt_set: prompt_source.PromptSet) -> list[prompt_source.Resolved]:
    """이번 평가에 쓴 판 가운데 Langfuse에서 가져온 것 (운영으로 옮길 후보)."""
    return [r for r in prompt_set.values() if r.source == "LANGFUSE"]


def promote_block(*, label: str, status: str, repeat: int, min_repeat: int,
                  has_baseline: bool, note: str | None, regression: bool,
                  candidates: list) -> str | None:
    """운영으로 옮기지 못하는 이유. 옮길 수 있으면 None (판단은 코드, CR-01)."""
    if label == PRODUCTION:
        return "운영 판을 평가했습니다. RFP_LANGFUSE_LABEL=staging처럼 다른 표시로 평가하세요."
    if not candidates:
        return "Langfuse에서 가져온 판이 없습니다(모두 코드 판)."
    if status != "DONE":
        return "평가가 끝나지 않았습니다."
    if repeat < min_repeat:
        return f"기준선과 같게 {min_repeat}번 이상 반복해 평가하세요(--repeat {min_repeat})."
    if not has_baseline or note:
        return f"비교할 기준선이 없습니다({note or '기준선 없음'})."
    if regression:
        return "기준선보다 나빠져(회귀) 옮기지 않습니다."
    return None


def promote(candidates: list[prompt_source.Resolved]) -> list[str]:
    """평가를 통과한 Langfuse 버전에 운영 표시를 붙인다.

    한 표시는 한 버전에만 붙으므로 예전 운영 판에서는 빠진다(되돌리기는 표시를 다시 옮김).
    """
    lf = _client()
    done = []
    try:
        for r in candidates:
            lf.set_labels(prompt_source.name_of(r.role), r.langfuse_version, [PRODUCTION])
            done.append(f"{r.role} {r.version}")
    except (httpx.TransportError, httpx.HTTPStatusError) as exc:
        raise LangfuseError(f"Langfuse 요청 실패: {exc}") from exc
    prompt_source.clear_cache()
    return done


def push_traces(conn: psycopg.Connection, run_id: int) -> int:
    """검토 실행 하나의 AI 호출 기록(OTLP JSON, 원문 없이 해시만)을 Langfuse로 보낸다."""
    body = ai_calls.otel(conn, run_id)
    spans = sum(len(s["spans"]) for r in body["resourceSpans"] for s in r["scopeSpans"])
    if not spans:
        return 0
    try:
        _client().push_traces(body)
    except (httpx.TransportError, httpx.HTTPStatusError) as exc:
        raise LangfuseError(f"Langfuse 요청 실패: {exc}") from exc
    return spans


# ── 평가셋 → 데이터셋, 평가 → 실험 (add-langfuse-experiments) ──────────────────

DATASET_PREFIX = "rfp-eval-"
PRIVATE_REFUSED = "비공개 평가셋(data/private)은 외부로 보내지 않습니다."
RECORD_OFF = "Langfuse 기록이 꺼져 있습니다(RFP_LANGFUSE_RECORD=on으로 켭니다)."


def record_enabled() -> bool:
    return get_settings().rfp_langfuse_record == "on"


def dataset_name(set_name: str) -> str:
    return f"{DATASET_PREFIX}{set_name}"


def item_id(set_name: str, item_no: str) -> str:
    # Langfuse 항목 id는 프로젝트 안에서 하나라 평가셋 이름을 붙인다
    return f"{set_name}-{item_no}"


@dataclass
class DatasetPushed:
    name: str
    dataset_id: str | None
    items: int
    url: str | None


def _url(lf: prompt_source.Client, dataset_id: str | None) -> str | None:
    """데이터셋 화면 주소. 프로젝트·데이터셋 id를 얻지 못하면 None (보낸 것은 그대로 성공)."""
    if not dataset_id:
        return None
    try:
        project = lf.project_id()
    except (httpx.TransportError, httpx.HTTPStatusError, ValueError):
        return None
    if not project:
        return None
    return f"{str(lf.http.base_url).rstrip('/')}/project/{project}/datasets/{dataset_id}"


def _ensure_dataset(lf: prompt_source.Client, evalset) -> dict:
    name = dataset_name(evalset.name)
    found = lf.get_dataset(name)
    if found is None:
        found = lf.create_dataset(name, f"RFP 프롬프트 평가셋 {evalset.name} (data/eval)",
                                  {"set_name": evalset.name, "source": "rfp-agent"})
    return found


def push_dataset(evalset, private: bool, items: list | None = None) -> DatasetPushed:
    """평가셋 문항을 데이터셋 항목으로 올린다(id 고정이라 다시 올려도 늘지 않음).

    items를 주면 그 문항만(화면 평가처럼 한 역할만 돌린 경우). 비공개 평가셋은 거절.
    """
    if private:
        raise LangfuseError(PRIVATE_REFUSED)
    lf = _client()
    name = dataset_name(evalset.name)
    try:
        ds = _ensure_dataset(lf, evalset)
        chosen = evalset.items if items is None else items
        for it in chosen:
            meta = {"role": it.role, "made_by": it.made_by, "set_version": evalset.version}
            if it.injection_of:
                meta["injection_of"] = it.injection_of
            lf.upsert_dataset_item(name, item_id(evalset.name, it.id), it.input, it.expected, meta)
    except (httpx.TransportError, httpx.HTTPStatusError) as exc:
        raise LangfuseError(f"Langfuse 요청 실패: {exc}") from exc
    return DatasetPushed(name, ds.get("id"), len(chosen), _url(lf, ds.get("id")))


def _hex(text: str, n: int) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:n]


def experiment_spans(result, prompt_set: prompt_source.PromptSet, dataset_id: str | None,
                     repeat_no: int, ended_ns: int) -> tuple[dict, list[dict]]:
    """반복 하나를 실험 하나로: 문항마다 trace 하나(뿌리 span 하나)와 점수 `ok`.

    실험·항목 연결은 Langfuse OpenTelemetry 실험 속성으로 한다. 정답 여부는 코드가 정한 값
    (prompt_eval, CR-01)을 옮겨 적기만 한다. 답 없음은 점수를 보내지 않는다.
    """
    exp = f"eval-{result.eval_id}-r{repeat_no}"
    set_name = result.set.name
    spans, scores = [], []
    answers = result.answers[repeat_no - 1]
    for item, a in zip(result.set.items, answers, strict=True):
        key = f"eval-{result.eval_id}-{repeat_no}-{item.id}"
        trace_id, span_id = _hex(key, 32), _hex(key, 16)
        ms = a.ms or 0
        attrs = {
            "langfuse.trace.name": f"eval {item.role} {item.id}",
            "langfuse.experiment.id": exp, "langfuse.experiment.name": exp,
            "langfuse.experiment.description":
                f"평가 {result.eval_id} · 반복 {repeat_no} · {result.label}",
            "langfuse.experiment.metadata.eval_id": result.eval_id,
            "langfuse.experiment.metadata.set_version": result.set.version,
            "langfuse.experiment.metadata.model": result.model or "",
            "langfuse.experiment.item.id": item_id(set_name, item.id),
            "langfuse.experiment.item.root_observation_id": span_id,
            "langfuse.experiment.item.expected_output": json.dumps(item.expected,
                                                                   ensure_ascii=False),
            "langfuse.observation.input": json.dumps(item.input, ensure_ascii=False),
            "langfuse.observation.output": json.dumps(a.answer, ensure_ascii=False),
            "gen_ai.request.model": result.model or "",
            "rfp.role": item.role, "rfp.item_id": item.id, "rfp.made_by": item.made_by,
        }
        if dataset_id:
            attrs["langfuse.experiment.dataset.id"] = dataset_id
        if a.error:
            attrs["rfp.error"] = a.error
        r = prompt_set.get(item.role)
        if r is not None:
            attrs["rfp.prompt_version"] = r.version
            if r.source == "LANGFUSE" and r.langfuse_version:
                attrs["langfuse.observation.prompt.name"] = prompt_source.name_of(item.role)
                attrs["langfuse.observation.prompt.version"] = r.langfuse_version
        spans.append({
            "traceId": trace_id, "spanId": span_id, "name": f"eval {item.role}", "kind": 3,
            "startTimeUnixNano": str(ended_ns - ms * 1_000_000),
            "endTimeUnixNano": str(ended_ns),
            "attributes": [ai_calls._attr(k, v) for k, v in attrs.items()],
            "status": {"code": 1 if a.ok is not None else 2},
        })
        if a.ok is not None:
            scores.append({"id": f"{trace_id}-ok", "traceId": trace_id, "observationId": span_id,
                           "name": "ok", "value": 1 if a.ok else 0, "dataType": "NUMERIC",
                           "comment": "코드 채점(prompt_eval)"})
    otlp = {"resourceSpans": [{
        "resource": {"attributes": [ai_calls._attr("service.name", "rfp-agent"),
                                    ai_calls._attr("rfp.eval_id", result.eval_id)]},
        "scopeSpans": [{"scope": {"name": "rfp_agent.prompt_eval"}, "spans": spans}],
    }]}
    return otlp, scores


def record_experiment(result, prompt_set: prompt_source.PromptSet, private: bool) -> str | None:
    """끝나 저장된 평가를 Langfuse 실험으로 남기고 데이터셋 화면 주소를 돌려준다.

    끈 설정·비공개 평가셋·끝나지 않은 평가는 LangfuseError(이유).
    평가 기록은 부르는 쪽이 이미 저장했다.
    """
    if not record_enabled():
        raise LangfuseError(RECORD_OFF)
    if result.status != "DONE" or result.eval_id is None:
        raise LangfuseError("끝나 저장된 평가만 보냅니다.")
    pushed = push_dataset(result.set, private)
    lf = _client()
    ended_ns = time.time_ns()
    try:
        for n in range(1, len(result.answers) + 1):
            otlp, scores = experiment_spans(result, prompt_set, pushed.dataset_id, n, ended_ns)
            lf.push_traces(otlp)
            lf.create_scores(scores)
    except (httpx.TransportError, httpx.HTTPStatusError) as exc:
        raise LangfuseError(f"Langfuse 요청 실패: {exc}") from exc
    return pushed.url


def save_url(conn: psycopg.Connection, eval_id: int, url: str | None) -> None:
    conn.execute("UPDATE prompt_eval_run SET langfuse_url = %s WHERE eval_id = %s", (url, eval_id))


# ── 검토 실행 작업 끝에 호출 기록 보내기 (add-langfuse-trace-push) ──────────────────

def send_run(conn: psycopg.Connection, run_id: int, token: str | None) -> str | None:
    """기록을 켰으면 검토의 AI 호출 기록을 보내고 결과를 검토 줄에 남긴다. 돌려주는 값은 상태.

    SENT(보냄) · FAILED(보내지 못함, 이유는 langfuse_error) · None(꺼짐·호출 없음, 남기지 않음).
    보내지 못해도 예외를 올리지 않는다(검토 단계·결과는 그대로).
    """
    if not record_enabled():
        return None
    try:
        sent = push_traces(conn, run_id)
        if not sent:
            return None
        lf = _client()
        url = None
        if token:
            try:
                project = lf.project_id()
            except (httpx.TransportError, httpx.HTTPStatusError, ValueError):
                project = None
            if project:
                trace_id = ai_calls._hex(f"run-{run_id}-{token}", 32)
                url = f"{str(lf.http.base_url).rstrip('/')}/project/{project}/traces/{trace_id}"
        conn.execute("UPDATE review_run SET langfuse_sent_at = now(), langfuse_url = %s, "
                     "langfuse_error = NULL WHERE run_id = %s", (url, run_id))
        conn.commit()
        return "SENT"
    except LangfuseError as exc:
        conn.rollback()
        conn.execute("UPDATE review_run SET langfuse_error = %s WHERE run_id = %s",
                     (str(exc)[:300], run_id))
        conn.commit()
        return "FAILED"


def sent_info(conn: psycopg.Connection, run_id: int) -> dict | None:
    """실행 기록 화면용: 보낸 적이 있거나 실패한 적이 있을 때만."""
    row = conn.execute("SELECT langfuse_sent_at, langfuse_url, langfuse_error FROM review_run "
                       "WHERE run_id = %s", (run_id,)).fetchone()
    if row is None or (row[0] is None and row[2] is None):
        return None
    return {"sent_at": row[0], "url": row[1], "error": row[2]}
