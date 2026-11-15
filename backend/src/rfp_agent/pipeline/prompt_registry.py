"""프롬프트 관리 화면용 조회 (add-prompt-view). 읽기만 한다.

프롬프트 글과 판은 코드(`llm/tasks.py`의 PROMPTS)가 정한다. 화면에서 고치지 않는다:
판을 올리면 해시 테스트와 평가를 거치게 하려는 것(design.md). Langfuse를 켜면(add-langfuse-prompts)
글은 Langfuse에서 고치고, 이 화면은 지금 어느 판을 가져왔는지만 보인다.
판마다 쓴 기간·검토 수는 실행 기록(review_run.graph_state)에서, AI 호출 수는 ai_call에서,
평가 점수는 prompt_eval_run에서 모은다. 새 표는 없다.
"""

import psycopg
from psycopg.rows import dict_row

from rfp_agent.config import get_settings
from rfp_agent.llm import prompt_source, tasks
from rfp_agent.pipeline import prompt_eval

ROLE_LABELS = {
    "classify": "문서 분류", "label": "문장 구분", "type": "유형", "risk": "위험 설명",
    "verify": "검증", "draft": "문장 초안", "handoff": "협조 질문", "assistant": "검토 도우미",
}
SOURCE = "backend/src/rfp_agent/llm/tasks.py"


def _usage(conn: psycopg.Connection) -> dict[tuple[str, str], dict]:
    """(역할, 판) → 쓴 검토 수·처음·마지막 시각. 역할별 판 도입 전 실행은 세지 않는다."""
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute("""
            SELECT kv.key AS role, kv.value AS version, count(*) AS runs,
                   min(r.started_at) AS first_used, max(r.started_at) AS last_used
            FROM review_run r,
                 jsonb_each_text(CASE WHEN jsonb_typeof(r.graph_state->'prompt_versions') = 'object'
                                      THEN r.graph_state->'prompt_versions' ELSE '{}'::jsonb END) kv
            GROUP BY kv.key, kv.value""").fetchall()
    return {(r["role"], r["version"]): r for r in rows}


def _calls(conn: psycopg.Connection) -> dict[tuple[str, str], int]:
    with conn.cursor() as cur:
        rows = cur.execute("""
            SELECT role, prompt_version, count(*) FROM ai_call
            WHERE role IS NOT NULL AND prompt_version IS NOT NULL
            GROUP BY role, prompt_version""").fetchall()
    return {(role, ver): n for role, ver, n in rows}


def _evals(conn: psycopg.Connection) -> dict[tuple[str, str], dict]:
    """(역할, 판) → 가장 최근 끝난 평가의 주 지표 (반복 최솟값)."""
    out: dict[tuple[str, str], dict] = {}
    for run in prompt_eval.runs(conn, limit=500):          # 최신순
        if run["status"] != "DONE":
            continue
        for role, metrics in (run["metrics"] or {}).items():
            ver = (run["prompt_versions"] or {}).get(role)
            if not ver or (role, ver) in out or role not in prompt_eval.METRICS:
                continue
            key = prompt_eval.primary_metric(role)
            m = metrics.get(key)
            if not m:
                continue
            out[(role, ver)] = {
                "eval_id": run["eval_id"], "created_at": run["created_at"],
                "set_name": run["set_name"], "model": run["model"],
                "metric": prompt_eval._metric_name(role, key), "min": m.get("min"),
                "weak": bool(m.get("weak")), "is_baseline": run["is_baseline"],
            }
    return out


def overview(conn: psycopg.Connection) -> dict:
    """역할마다 지금 판과 판 기록(쓴 기간·검토 수·AI 호출 수·평가 점수). 판은 처음 쓴 순서."""
    usage, calls, evals = _usage(conn), _calls(conn), _evals(conn)
    # 지금 쓰는 판: Langfuse를 켰으면 가져온 판, 아니면 코드 판 (add-langfuse-prompts)
    found = prompt_source.resolve()
    roles = []
    for role in tasks.PROMPTS:
        now = found[role]
        current = now.version
        vers = {v for (r, v) in (*usage, *calls, *evals) if r == role} | {current}
        rows = []
        for v in vers:
            u = usage.get((role, v), {})
            rows.append({
                "version": v, "current": v == current,
                "runs": u.get("runs", 0), "first_used": u.get("first_used"),
                "last_used": u.get("last_used"), "calls": calls.get((role, v), 0),
                "eval": evals.get((role, v)),
            })
        # 처음 쓴 순서, 쓴 적 없는 판은 뒤. 같으면 판 이름순 (CR-11)
        rows.sort(key=lambda x: (x["first_used"] is None, x["first_used"] or 0, x["version"]))
        roles.append({
            "role": role, "label": ROLE_LABELS.get(role, role), "current": current,
            "evaluated": role in prompt_eval.METRICS,
            "in_doc_key": role in tasks.DOC_ROLES, "versions": rows,
            "prompt_source": now.source, "langfuse_name": prompt_source.name_of(role),
            "langfuse_version": now.langfuse_version,
            "fallback": prompt_source.FALLBACKS.get(now.fallback) if now.fallback else None,
        })
    s = get_settings()
    return {"source": SOURCE, "doc_key": ".".join(found[r].version for r in tasks.DOC_ROLES),
            "roles": roles,
            "langfuse": {"enabled": prompt_source.enabled(), "label": s.rfp_langfuse_label,
                         "host": s.langfuse_host if prompt_source.enabled() else None}}
