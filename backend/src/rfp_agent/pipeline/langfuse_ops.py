"""Langfuse에 프롬프트를 올리고, 평가를 통과한 판만 운영 표시로 옮기고, 호출 기록을 보낸다
(add-langfuse-prompts, ADR-010). 사람이 돌리는 명령(rfp-db)에서만 부른다.
"""

from dataclasses import dataclass

import httpx
import psycopg

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
