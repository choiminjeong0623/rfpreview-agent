"""실행 기록.

명세 review-run "실행 기록 저장"의 Scenario (change add-run-log).
"""

from rfp_agent.pipeline import run_log
from rfp_agent.pipeline.run import RunContext, create_run, execute_run

VERSION = "test-dict-v1"


def run(db, llm, paths):
    run_id = create_run(db, VERSION, llm)
    stage = execute_run(RunContext(db, VERSION, llm, None), run_id, paths)
    return run_id, stage


def row(db, run_id):
    return next(r for r in run_log.run_log(db) if r["run_id"] == run_id)


def test_run_log_saved(db, spec, fake_llm):
    """Scenario: 실행 기록 저장 — AI 사용량, 단계별 시간, 걸린 시간이 남는다."""
    run_id, stage = run(db, fake_llm, [spec])
    assert stage == "ENGINEER_REVIEW"
    r = row(db, run_id)
    calls = len(fake_llm.prompts)
    assert calls > 0
    assert (r["llm_calls"], r["llm_retries"]) == (calls, 0)
    assert (r["llm_input_tokens"], r["llm_output_tokens"], r["llm_thinking_tokens"]) == \
        (100 * calls, 10 * calls, 5 * calls)
    assert r["seconds"] is not None and r["seconds"] >= 0
    steps = [s["step"] for s in r["steps"]]
    assert steps[:4] == ["documents", "pairs", "risks", "judge"] and steps[-1] == "assign"
    assert all(s["seconds"] is not None and s["attempt"] == 0 for s in r["steps"])
    assert r["documents"] == 1 and r["documents_reused"] == 0 and r["judgments"] > 0
    assert r["llm_model"] == "fake-model" and r["estimated_cost_krw"] is None   # 단가표에 없음


def test_run_log_reused_document(db, spec, fake_llm):
    """Scenario: 같은 파일을 다시 처리 — 다시 쓴 문서 1개, 문서 읽기 AI 호출이 줄어든다."""
    first, _ = run(db, fake_llm, [spec])
    second, _ = run(db, fake_llm, [spec])
    a, b = row(db, first), row(db, second)
    assert (a["documents_reused"], b["documents_reused"]) == (0, 1)
    assert b["llm_calls"] < a["llm_calls"]


def test_run_log_counts_retries(db, spec):
    """Scenario: AI 재시도 기록 — 계속 실패하면 재시도 수와 실패 단계가 남는다."""
    from tests.conftest import FakeLLM
    llm = FakeLLM(fail=True)
    run_id, stage = run(db, llm, [spec])
    assert stage == "FAILED"
    r = row(db, run_id)
    assert (r["llm_calls"], r["llm_retries"]) == (3, 2)              # 처음 1번 + 재시도 2번 (CR-12)
    assert r["stage"] == "FAILED" and r["failed_step"] == "documents"
    assert r["steps"] and r["steps"][-1]["seconds"] is not None


def test_run_log_without_ai(db, spec):
    """Scenario: 언어 모델 없이 돈 실행 — 호출 0, 비용 0, 팀 가정 표시 없음."""
    run_id, _ = run(db, None, [spec])
    r = row(db, run_id)
    assert (r["llm_calls"], r["estimated_cost_krw"], r["cost_assumed"]) == (0, 0, False)


def test_estimated_cost():
    """Scenario: 단가로 어림한 비용 — 단가는 팀 가정, 파일 1 실측 토큰이면 약 680원."""
    cost = run_log.estimated_cost_krw("gemini-3.8-flash", 73_556, 28_775, 77_778)
    assert 650 <= cost <= 720
    assert run_log.estimated_cost_krw("모르는 모델", 1, 1, 1) is None
