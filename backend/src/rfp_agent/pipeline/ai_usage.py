"""분석 밖 AI 사용량 (add-ai-usage-log).

검토 도우미·협조 요청 확인할 점·다시 만들기처럼 분석 실행 밖에서 AI를 부른 요청마다
사용량 한 줄을 남긴다. 분석 실행의 사용량은 review_run(add-run-log)에 있다.
"""

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from rfp_agent.llm.client import usage_of
from rfp_agent.pipeline.run_log import estimated_cost_krw

FEATURES = {
    "ASSISTANT": "검토 도우미",
    "HANDOFF_ASK": "협조 요청 확인할 점",
    "PRODUCT_SWITCH": "비교 제품 바꾸기",
    "LOSS_EDIT": "손실값 고치기",
    "REVIEW_ACTION": "확정·수정 뒤 다시 만들기",
    "BULK_CONFIRM": "한꺼번에 확정",
    "ANALYSIS": "분석",                 # review_run 사용량 (응답에서만)
}


@contextmanager
def tracked(conn: psycopg.Connection, feature: str, run_id: int | None,
            llm: object) -> Iterator[object]:
    """요청 처리 뒤(오류여도) AI를 1번 이상 불렀으면 사용량 한 줄을 남긴다.

    이미 부른 호출은 비용이 나갔으므로 처리 중 오류로 트랜잭션이 깨졌어도 되돌린 뒤 남긴다.
    """
    usage = usage_of(llm)
    before = usage.copy() if usage else None
    failed = False
    try:
        yield llm
    except BaseException:
        failed = True
        raise
    finally:
        if usage is not None and before is not None:
            used = usage.minus(before)
            if used.calls > 0:
                if failed:
                    conn.rollback()
                conn.execute(
                    """INSERT INTO ai_usage (feature, run_id, model, calls, retries, input_tokens,
                                             output_tokens, thinking_tokens)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                    (feature, run_id, getattr(llm, "model", None), used.calls, used.retries,
                     used.input_tokens, used.output_tokens, used.thinking_tokens))
                conn.commit()


def summary(conn: psycopg.Connection, days: int = 30) -> dict:
    """최근 days일의 날짜(DB 날짜)·기능별 사용량과 추정 비용. 분석 실행은 기능 ANALYSIS."""
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            """SELECT day, feature, model, sum(calls)::int AS calls, sum(retries)::int AS retries,
                      sum(input_tokens)::bigint AS input_tokens,
                      sum(output_tokens)::bigint AS output_tokens,
                      sum(thinking_tokens)::bigint AS thinking_tokens
                 FROM (SELECT used_at::date AS day, feature, model, calls, retries, input_tokens,
                              output_tokens, thinking_tokens
                         FROM ai_usage WHERE used_at >= CURRENT_DATE - %(days)s
                       UNION ALL
                       SELECT started_at::date, 'ANALYSIS', llm_model, llm_calls, llm_retries,
                              llm_input_tokens, llm_output_tokens, llm_thinking_tokens
                         FROM review_run
                        WHERE llm_calls > 0 AND started_at >= CURRENT_DATE - %(days)s) u
                GROUP BY day, feature, model ORDER BY day DESC, feature, model""",
            {"days": days}).fetchall()
    for r in rows:
        r["feature_name"] = FEATURES[r["feature"]]
        r["estimated_cost_krw"] = estimated_cost_krw(r["model"], r["input_tokens"],
                                                     r["output_tokens"], r["thinking_tokens"])
    costs = [r["estimated_cost_krw"] for r in rows]
    return {"days": days, "items": rows, "total_calls": sum(r["calls"] for r in rows),
            "total_cost_krw": None if any(c is None for c in costs) else sum(costs)}
