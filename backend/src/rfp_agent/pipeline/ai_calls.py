"""검토의 AI 호출 기록 조회와 OpenTelemetry 형식 내보내기 (add-ai-call-trace, FR-21).

읽기만 한다. "다른 답"은 이 검토 호출 중, 입력 해시가 같은 다른 호출(다른 검토 포함)과 출력 해시가
다른 성공 호출 수다 (재현성 점검, CR-11).
"""

import hashlib
from collections import Counter

import psycopg
from psycopg.rows import dict_row

COLUMNS = """call_id, step, role, model, prompt_version, attempt, started_at, ended_at,
             duration_ms, input_tokens, output_tokens, thinking_tokens, result, dropped_reason,
             input_hash, output_hash, batch_lines, run_token::text AS run_token, feature"""


def calls(conn: psycopg.Connection, run_id: int) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(f"SELECT {COLUMNS} FROM ai_call WHERE run_id = %s ORDER BY call_id",
                           (run_id,)).fetchall()


def different_answers(conn: psycopg.Connection, run_id: int) -> int:
    return conn.execute(
        """SELECT count(*) FROM ai_call a
           WHERE a.run_id = %s AND a.result = 'OK' AND EXISTS (
             SELECT 1 FROM ai_call b WHERE b.input_hash = a.input_hash
               AND b.call_id <> a.call_id AND b.result = 'OK'
               AND b.output_hash IS DISTINCT FROM a.output_hash)""", (run_id,)).fetchone()[0]


def summary(conn: psycopg.Connection, run_id: int) -> dict:
    rows = calls(conn, run_id)
    by_step: dict[str, int] = {}
    for r in rows:
        key = r["step"] or "—"
        by_step[key] = by_step.get(key, 0) + r["duration_ms"]
    # run_token은 내보내기(otel)에서만 쓴다. 화면 응답 모양(AiCall)에는 없다
    shown = [{k: v for k, v in r.items() if k != "run_token"} for r in rows]
    return {"calls": shown, "count": len(rows),
            "by_result": dict(Counter(r["result"] for r in rows)),
            "step_ms": [{"step": k, "ms": v} for k, v in by_step.items()],
            "different_answers": different_answers(conn, run_id) if rows else 0}


def _hex(text: str, n: int) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:n]


def _nanos(dt) -> str:
    return str(int(dt.timestamp() * 1_000_000_000))


def _attr(key: str, value) -> dict:
    if isinstance(value, bool):
        return {"key": key, "value": {"boolValue": value}}
    if isinstance(value, int):
        return {"key": key, "value": {"intValue": str(value)}}
    return {"key": key, "value": {"stringValue": str(value)}}


def otel(conn: psycopg.Connection, run_id: int) -> dict:
    """OTLP JSON (resourceSpans). 호출마다 span 하나, 생성형 AI 이름 규칙(gen_ai.*)을 따른다.

    trace id는 검토 번호와 실행 토큰에서 만들어 같은 실행의 호출이 한 trace로 묶인다.
    외부로 보내지 않는다(사람이 내려받아 다른 추적 도구에 넣는다).
    """
    spans = []
    for c in calls(conn, run_id):
        attrs = {"gen_ai.operation.name": "chat", "gen_ai.request.model": c["model"] or "",
                 "gen_ai.usage.input_tokens": c["input_tokens"],
                 "gen_ai.usage.output_tokens": c["output_tokens"],
                 "rfp.role": c["role"] or "", "rfp.prompt_version": c["prompt_version"] or "",
                 "rfp.step": c["step"] or "", "rfp.feature": c["feature"],
                 "rfp.attempt": c["attempt"], "rfp.result": c["result"],
                 "rfp.input_hash": c["input_hash"], "rfp.output_hash": c["output_hash"] or "",
                 "rfp.batch_lines": c["batch_lines"]}
        if c["dropped_reason"]:
            attrs["rfp.dropped_reason"] = c["dropped_reason"]
        spans.append({
            "traceId": _hex(f"run-{run_id}-{c['run_token'] or ''}", 32),
            "spanId": _hex(f"call-{c['call_id']}", 16),
            "name": f"chat {c['role'] or 'ai'}",
            "kind": 3,                                        # SPAN_KIND_CLIENT
            "startTimeUnixNano": _nanos(c["started_at"]),
            "endTimeUnixNano": _nanos(c["ended_at"]),
            "attributes": [_attr(k, v) for k, v in attrs.items()],
            "status": {"code": 1 if c["result"] == "OK" else 2},
        })
    return {"resourceSpans": [{
        "resource": {"attributes": [_attr("service.name", "rfp-agent"),
                                    _attr("rfp.run_id", run_id)]},
        "scopeSpans": [{"scope": {"name": "rfp_agent.llm.trace"}, "spans": spans}],
    }]}
