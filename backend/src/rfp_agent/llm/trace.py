"""AI 호출 기록 (add-ai-call-trace, FR-21·NFR-14).

AI 문장 요청(call_with_retry)을 시도마다 한 건씩 기록한다. 원문은 기본으로 남기지 않고 해시만
남긴다(NFR-06·07). 원문은 RFP_TRACE_RAW=on일 때만 따로 저장하고 7일 뒤 지운다.

기록은 세션(contextvar)에 모으고, 세션 주인(분석 실행·검토 도우미·협조 질문·평가)이 자기 DB 연결로
저장한다. 세션이 없으면 기록하지 않는다. 기록은 처리 결과를 바꾸지 않고, 저장이 실패해도 처리는
계속한다.
"""

import contextvars
import hashlib
import json
import logging
import re
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime

import psycopg

from rfp_agent.config import get_settings

log = logging.getLogger(__name__)

RAW_KEEP_DAYS = 7               # 원문 보관 기간 [제안]
RESULTS = ("OK", "FORMAT_ERROR", "CONFIG_ERROR", "TIMEOUT", "CONNECTION_ERROR")
_NUMBERED = re.compile(r"^\d+\. ", re.MULTILINE)


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def raw_enabled() -> bool:
    return get_settings().rfp_trace_raw == "on"


@dataclass
class Call:
    role: str | None
    model: str | None
    prompt_version: str | None
    step: str | None
    attempt: int
    started_at: datetime
    ended_at: datetime
    input_tokens: int
    output_tokens: int
    thinking_tokens: int
    result: str
    input_hash: str
    output_hash: str | None
    batch_lines: int
    dropped_reason: str | None = None
    prompt: str | None = None               # 원문 저장을 켰을 때만
    answer: str | None = None

    @property
    def duration_ms(self) -> int:
        return int((self.ended_at - self.started_at).total_seconds() * 1000)


@dataclass
class Session:
    run_id: int | None
    token: str | None
    feature: str
    step: str | None = None
    calls: list[Call] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)


_session: contextvars.ContextVar[Session | None] = contextvars.ContextVar("ai_trace",
                                                                          default=None)
_last = threading.local()                   # 이 스레드의 마지막 기록 (버린 이유를 붙이려고)


@contextmanager
def session(run_id: int | None, feature: str, token: str | None = None) -> Iterator[Session]:
    """이 안의 AI 호출을 모은다. 빠져나갈 때 저장하지는 않는다(주인이 flush)."""
    s = Session(run_id, token, feature)
    reset = _session.set(s)
    try:
        yield s
    finally:
        _session.reset(reset)


def current() -> Session | None:
    return _session.get()


def set_step(step: str) -> None:
    if (s := _session.get()) is not None:
        s.step = step


def record(role: str | None, model: str | None, attempt: int, started_at: datetime,
           prompt: str, schema: dict, result: str, answer: dict | None,
           tokens: tuple[int, int, int]) -> None:
    s = _session.get()
    _last.call = None
    if s is None:
        return
    from rfp_agent.llm.tasks import PROMPTS

    answer_text = json.dumps(answer, sort_keys=True, ensure_ascii=False) \
        if answer is not None else None
    keep = raw_enabled()
    call = Call(role, model, PROMPTS.get(role or ""), s.step, attempt, started_at,
                datetime.now(UTC), *tokens, result,
                digest(prompt + "\n" + json.dumps(schema, sort_keys=True, ensure_ascii=False)),
                digest(answer_text) if answer_text is not None else None,
                len(_NUMBERED.findall(prompt)),
                prompt=prompt if keep else None, answer=answer_text if keep else None)
    with s.lock:
        s.calls.append(call)
    _last.call = call


def drop(reason: str) -> None:
    """이 스레드의 마지막 호출이 코드 검사에서 버려졌음을 적는다 (위험 설명 근거 대조 등)."""
    call = getattr(_last, "call", None)
    if call is not None:
        call.dropped_reason = reason


def result_of(exc: Exception | None) -> str:
    """호출 결과 종류. 형식·설정 오류는 부르는 쪽이 정한다."""
    if exc is None:
        return "OK"
    name = type(exc).__name__.lower()
    if isinstance(exc, TimeoutError) or "timeout" in name or "timeout" in str(exc).lower():
        return "TIMEOUT"
    return "CONNECTION_ERROR"


def flush(conn: psycopg.Connection, s: Session | None = None) -> int:
    """모은 기록을 이 연결로 저장한다(부르는 쪽 트랜잭션 안). 저장한 수. 실패하면 경고만."""
    s = s or _session.get()
    if s is None:
        return 0
    with s.lock:
        calls, s.calls = s.calls, []
    if not calls:
        return 0
    try:
        with conn.transaction():
            for c in calls:
                call_id = conn.execute(
                    """INSERT INTO ai_call (run_id, run_token, feature, step, role, model,
                         prompt_version, attempt, started_at, ended_at, duration_ms,
                         input_tokens, output_tokens, thinking_tokens, result, dropped_reason,
                         input_hash, output_hash, batch_lines)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                               %s, %s, %s) RETURNING call_id""",
                    (s.run_id, s.token, s.feature, c.step, c.role, c.model, c.prompt_version,
                     c.attempt, c.started_at, c.ended_at, c.duration_ms, c.input_tokens,
                     c.output_tokens, c.thinking_tokens, c.result, c.dropped_reason,
                     c.input_hash, c.output_hash, c.batch_lines)).fetchone()[0]
                if c.prompt is not None:
                    conn.execute("INSERT INTO ai_call_raw (call_id, prompt, answer) "
                                 "VALUES (%s, %s, %s)", (call_id, c.prompt, c.answer))
    except psycopg.Error as exc:
        log.warning("AI 호출 기록 저장 실패 (%s건): %s", len(calls), exc)
        return 0
    return len(calls)


def purge(conn: psycopg.Connection) -> int:
    """보관 기간이 지난 원문만 지운다. 호출 기록은 남는다."""
    try:
        n = conn.execute("DELETE FROM ai_call_raw WHERE created_at < now() - "
                         "make_interval(days => %s)", (RAW_KEEP_DAYS,)).rowcount
        conn.commit()
        return n
    except psycopg.Error as exc:
        conn.rollback()
        log.warning("AI 호출 원문 지우기 실패: %s", exc)
        return 0
