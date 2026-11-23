"""AI 호출 운영 지표·평가 중 비용 상한·사람 수정 비율 (change add-ops-metrics).

명세 review-run "역할별 AI 호출 지표", prompt-evaluation "비용 상한", evaluation "사람 수정 비율".
"""

import json

import pytest

from rfp_agent.pipeline import ai_calls
from rfp_agent.pipeline import prompt_eval as pe


def call(n, role, ms, result="OK", attempt=0, h=None, dropped=None):
    return {"call_id": n, "role": role, "duration_ms": ms, "result": result, "attempt": attempt,
            "input_hash": h or f"h{n:015d}", "dropped_reason": dropped}


def test_role_stats():
    """Scenario: 역할별 지표 — 요청·시도·실패율·재시도 뒤 성공·버린 비율."""
    rows = [call(1, "type", 900, "TIMEOUT", h="same"), call(2, "risk", 50, dropped="NUMBER"),
            call(3, "type", 100), call(4, "type", 120, attempt=1, h="same"),
            call(5, "type", 200), call(6, "type", 300), call(7, "type", 400)]
    stats = {s["role"]: s for s in ai_calls.role_stats(rows)}
    t = stats["type"]
    assert (t["requests"], t["attempts"], t["failure_rate"], t["recovered"]) == (5, 6, 16.7, 1)
    assert (t["p50_ms"], t["p95_ms"]) == (200, 900)
    assert t["dropped_rate"] == 0.0
    r = stats["risk"]
    assert (r["requests"], r["dropped_rate"], r["failure_rate"]) == (1, 100.0, 0.0)


def test_role_stats_scenario_numbers():
    """Scenario: 역할별 지표 — 재시도 성공 1 + 바로 성공 3 = 요청 4·시도 5·실패율 20 %."""
    rows = [call(1, "type", 100, "TIMEOUT", h="x"), call(2, "type", 100, attempt=1, h="x"),
            call(3, "type", 200), call(4, "type", 300), call(5, "type", 400)]
    [t] = ai_calls.role_stats(rows)
    assert (t["requests"], t["attempts"], t["failure_rate"], t["recovered"]) == (4, 5, 20.0, 1)


def test_role_stats_empty():
    """Scenario: 호출 기록 없음 — 역할별 표가 비어 있다."""
    assert ai_calls.role_stats([]) == []


@pytest.fixture
def priced(monkeypatch):
    """단가표에 시험 모델 "big"(입력 0, 출력 100달러/1M 토큰)을 더한다."""
    from rfp_agent.config import get_settings

    monkeypatch.setenv("RFP_EVAL_PRICES", "big=0/100")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def long_answers(extra_output: int):
    """정답대로 답하되 답마다 출력 토큰을 extra_output만큼 더 쓰는 순차(1개씩) 대역."""
    from tests.test_prompt_eval import Scripted, answers_for

    class Long(Scripted):
        workers = 1

        def generate_json(self, prompt, schema):
            out = super().generate_json(prompt, schema)
            self.usage.add(output_tokens=extra_output)
            return out

    def make(evalset):
        return Long(answers_for(evalset), model="big")
    return make


def six_items():
    from tests.test_prompt_eval import jsonl, type_item

    return pe.parse_set("budget", jsonl([type_item(n) for n in range(6)]))


def test_budget_stops_midway(priced):
    """Scenario: 평가 중 상한을 넘음 — 남은 문항은 묻지 않고 실패, 이유에 상한·묻지 않은 수."""
    s = six_items()
    llm = long_answers(5000)(s)
    est = pe.estimate(s.items, 1, "big")
    assert est["cost_krw"] < 500                                   # 어림은 상한 아래
    result = pe.evaluate(s, llm, "GEMINI", repeat=1, max_krw=500)
    assert len(llm.prompts) == 1                                   # 첫 문항(약 750원) 뒤 멈춤
    assert result.status == "FAILED"
    assert "비용 상한 500원" in result.skip_reason and "묻지 않은 문항 5개" in result.skip_reason
    assert [a.error for a in result.answers[0]][1:] == ["BUDGET"] * 5


def test_budget_stops_remaining_repeats(priced):
    """반복 중 상한을 넘으면 남은 반복은 통째로 묻지 않는다."""
    s = six_items()
    llm = long_answers(500)(s)                                     # 문항당 약 76원, 반복당 약 455원
    result = pe.evaluate(s, llm, "GEMINI", repeat=3, max_krw=600, confirmed=False)
    assert result.status == "FAILED" and len(result.answers) == 2  # 3번째 반복은 시작하지 않음
    assert len(llm.prompts) == 8                                   # 1번째 6 + 2번째 2
    assert "묻지 않은 문항 10개" in result.skip_reason


def test_budget_confirmed_uses_double_estimate(priced):
    """확인 옵션으로 시작하면 상한이 아니라 상한과 어림 두 배 가운데 큰 값에서 멈춘다."""
    s = six_items()
    est = pe.estimate(s.items, 1, "big")["cost_krw"]
    with pytest.raises(pe.EvalError):
        pe.evaluate(s, long_answers(300)(s), "GEMINI", max_krw=100)
    llm = long_answers(300)(s)
    result = pe.evaluate(s, llm, "GEMINI", max_krw=100, confirmed=True)
    assert result.status == "DONE" and len(llm.prompts) == 6
    assert 100 < result.cost_krw <= max(100, est * 2)
    assert json.dumps(result.metrics)


def test_budget_stop_saved_without_baseline(priced, db):
    """멈춘 평가는 실패로 저장되고 예전 기준선을 풀지 않으며 보고서에 멈춤 이유가 있다."""
    s = six_items()
    db.execute("""INSERT INTO prompt_eval_run (set_name, set_version, ai_mode, prompt_versions,
                      repeat, status, metrics, is_baseline) VALUES ('budget', 'v', 'GEMINI', '{}',
                      3, 'DONE', '{}', TRUE)""")
    result = pe.evaluate(s, long_answers(5000)(s), "GEMINI", max_krw=500)
    pe.save(db, result, baseline=True)
    rows = db.execute("SELECT status, is_baseline FROM prompt_eval_run WHERE set_name = 'budget' "
                      "ORDER BY eval_id").fetchall()
    assert rows == [("DONE", True), ("FAILED", False)]
    assert "**멈춤**: 비용 상한" in pe.report(result, None)


def test_edit_rate(db, spec):
    """Scenario: 사람 수정 비율 — 한 줄씩 확정 3·수정 1·반려 1·한꺼번에 확정 2 → 2 / 5 = 40 %."""
    from rfp_agent.pipeline import evaluation, review
    from rfp_agent.pipeline.run import RunContext, create_run, execute_run
    from tests.test_evaluation import VERSION, act, comply_ids, metric

    run = create_run(db, VERSION, None)
    assert execute_run(RunContext(db, VERSION, None, None), run, [spec]) == "ENGINEER_REVIEW"
    ids = comply_ids(db, run, 7)
    for j in ids[:3]:
        act(db, run, j, "CONFIRM")
    act(db, run, ids[3], "EDIT", {"result": "DEVIATION_CANDIDATE"}, "값이 다름")
    act(db, run, ids[4], "REJECT", None, "요구사항 아님")
    out = review.bulk_confirm(RunContext(db, VERSION, None, None), run, ids[5:])
    assert out["confirmed"] == 2
    m = metric(evaluation.score(db, [run]), "EDIT-RATE")
    assert (m["num"], m["den"], m["value"]) == (2, 5, 40.0)
    assert m["note"] == "한꺼번에 확정 2줄 뺌" and m["better"] == "down" and m["passed"] is None
    assert m["ci_low"] is not None


def test_edit_rate_old_bulk_without_marker(db, spec):
    """표시가 없는 예전 한꺼번에 확정(같은 사람·같은 시각 둘 이상)도 분모에서 뺀다."""
    from rfp_agent.pipeline import evaluation, review
    from rfp_agent.pipeline.run import RunContext, create_run, execute_run
    from tests.test_evaluation import VERSION, act, comply_ids, metric

    run = create_run(db, VERSION, None)
    assert execute_run(RunContext(db, VERSION, None, None), run, [spec]) == "ENGINEER_REVIEW"
    ids = comply_ids(db, run, 3)
    act(db, run, ids[0], "CONFIRM")
    review.bulk_confirm(RunContext(db, VERSION, None, None), run, ids[1:])
    db.execute("UPDATE review_log SET reason = NULL WHERE reason = %s", (review.BULK_REASON,))
    m = metric(evaluation.score(db, [run]), "EDIT-RATE")
    assert (m["num"], m["den"], m["note"]) == (0, 1, "한꺼번에 확정 2줄 뺌")
