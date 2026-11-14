"""실행 기록 (add-run-log, NFR-09): 검토마다 걸린 시간, 단계별 시간, AI 사용량, 추정 비용.

비용은 저장하지 않고 여기서 모델 단가로 계산한다. 단가는 팀 가정이다(CR-06):
gemini-3.8-flash는 2026-10-25 파일 1 실측(입력 73,556 · 출력 28,775 · 생각 77,778 토큰 ≈ 680원)에
맞춘 값이다. 생각 토큰은 출력 단가로 센다. 표에 없는 모델은 비용을 비운다.
"""

import psycopg
from psycopg.rows import dict_row

from rfp_agent.pipeline.queries import REVIEW_INFO

USD_KRW = 1500                                   # 팀 가정 (비용 비교 문서와 같은 값)
PRICES_USD_PER_M = {                             # 모델: (입력, 출력·생각) 1M 토큰당 달러, 팀 가정
    "gemini-3.8-flash": (0.50, 4.00),
}


def estimated_cost_krw(model: str | None, input_tokens: int, output_tokens: int,
                       thinking_tokens: int) -> int | None:
    if model is None:
        return 0                                  # AI 없이 규칙만 쓴 실행
    price = PRICES_USD_PER_M.get(model)
    if price is None:
        return None
    usd = (input_tokens * price[0] + (output_tokens + thinking_tokens) * price[1]) / 1_000_000
    return round(usd * USD_KRW)


def run_log(conn: psycopg.Connection, limit: int = 200) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(f"""
            SELECT r.run_id, {REVIEW_INFO}, r.stage, r.failed_step, r.started_at, r.finished_at,
                   EXTRACT(EPOCH FROM r.finished_at - r.started_at)::float AS seconds,
                   r.llm_model, r.dict_version, r.llm_calls, r.llm_retries, r.llm_input_tokens,
                   r.llm_output_tokens, r.llm_thinking_tokens, r.documents_reused,
                   r.retry_count AS retries,
                   COALESCE((r.graph_state->>'type_examples')::int, 0) AS type_examples,
                   r.graph_state->>'resumed_from' AS resumed_from,
                   COALESCE((r.graph_state->>'documents_reprocessed')::int, 0)
                       AS documents_reprocessed,
                   COALESCE((r.graph_state->>'lines_reprocessed')::int, 0) AS lines_reprocessed,
                   r.cancel_requested_at IS NOT NULL AS cancelled,
                   (SELECT count(*) FROM run_document WHERE run_id = r.run_id) AS documents,
                   (SELECT count(*) FROM requirement q JOIN run_document rd USING (document_id)
                     WHERE rd.run_id = r.run_id AND q.req_kind = 'REQUIREMENT') AS requirements,
                   (SELECT count(*) FROM judgment WHERE run_id = r.run_id AND is_current)
                       AS judgments,
                   (SELECT count(*) FROM risk_flag WHERE run_id = r.run_id
                     AND explanation_drop_reason IS NOT NULL) AS explanations_dropped,
                   (SELECT count(*) FROM risk_flag WHERE run_id = r.run_id
                     AND explanation_check = 'NEEDS_REVIEW') AS explanations_unverified
            FROM review_run r ORDER BY r.run_id DESC LIMIT %s""", (limit,)).fetchall()
        steps = cur.execute(
            """SELECT run_id, attempt, step,
                      EXTRACT(EPOCH FROM finished_at - started_at)::float AS seconds
               FROM run_step_time WHERE run_id = ANY(%s)
               ORDER BY run_id, attempt, started_at""",
            ([r["run_id"] for r in rows],)).fetchall()
    by_run: dict[int, list[dict]] = {}
    for s in steps:
        by_run.setdefault(s.pop("run_id"), []).append(s)
    for r in rows:
        r["steps"] = by_run.get(r["run_id"], [])
        r["estimated_cost_krw"] = estimated_cost_krw(
            r["llm_model"], r["llm_input_tokens"], r["llm_output_tokens"],
            r["llm_thinking_tokens"])
        r["cost_assumed"] = r["llm_model"] is not None    # 단가가 팀 가정 (CR-06)
    return rows
