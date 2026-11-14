"""결재 흐름: 결재자를 골라 상신, 지정 결재자만 결정, 상신 취소. 명세 review-approval의 Scenario
(change update-approval-flow)."""

import pytest

from rfp_agent.pipeline import queries, review
from rfp_agent.pipeline.run import RunContext, create_run, execute_run

VERSION = "test-dict-v1"
COMMENT = "질의 1건은 10-27 회신 예정"


@pytest.fixture
def run(db, spec):
    run_id = create_run(db, VERSION, None)
    assert execute_run(RunContext(db, VERSION, None, None), run_id, [spec]) == "ENGINEER_REVIEW"
    return run_id


def user(conn, name, role):
    return conn.execute("INSERT INTO app_user (user_name, role) VALUES (%s, %s) "
                        "RETURNING user_id", (name, role)).fetchone()[0]


def approver(conn):
    return review.default_user(conn, "APPROVER")


def test_submit_with_approver_and_comment(db, run):
    """Scenario: 결재자와 의견을 넣고 상신."""
    engineer = review.default_user(db, "ENGINEER")
    result = review.finish_review(db, run, approver(db), COMMENT, engineer)
    assert result["stage"] == "APPROVAL"
    screen = review.approval(db, run)
    a = screen["approval"]
    assert a["requested_by"] == "기본 엔지니어" and a["requested_at"] is not None
    assert a["approver"] == "기본 승인자" and a["request_comment"] == COMMENT
    assert a["decision"] is None
    assert "AR-01" in [r["ar_code"] for r in screen["reasons"]]
    [entry] = [h for h in review.history(db, run) if h["target_table"] == "review_run"]
    assert entry["reason"] == COMMENT and entry["after_value"]["stage"] == "APPROVAL"


def test_run_without_criteria_still_waits(db, run, monkeypatch):
    """Scenario: 걸린 기준이 없는 실행 — 걸린 기준이 없어도 승인 대기가 된다."""
    monkeypatch.setattr(review, "criteria", lambda conn, run_id: [])
    result = review.finish_review(db, run, approver(db), "기준에 걸린 것 없음")
    assert result["stage"] == "APPROVAL" and result["criteria"] == []
    screen = review.approval(db, run)
    assert screen["reasons"] == [] and screen["approval"]["decision"] is None
    assert queries.run_summary(db, run)["stage"] == "APPROVAL"


@pytest.mark.parametrize("comment", ["", "   ", None])
def test_submit_without_comment(db, run, comment):
    """Scenario: 상신 의견 없이 상신."""
    with pytest.raises(review.ReviewError) as err:
        review.finish_review(db, run, approver(db), comment)
    assert err.value.status == 400 and "상신 의견" in str(err.value)
    assert queries.run_summary(db, run)["stage"] == "ENGINEER_REVIEW"


def test_submit_to_non_approver(db, run):
    """Scenario: 승인자가 아닌 결재자 — 견적 담당을 결재자로 고르면 거부된다."""
    cost = review.default_user(db, "COST")
    with pytest.raises(review.ReviewError) as err:
        review.finish_review(db, run, cost, COMMENT)
    assert err.value.status == 400 and "승인자만" in str(err.value)
    with pytest.raises(review.ReviewError) as err:          # 없는 사용자
        review.finish_review(db, run, 999999, COMMENT)
    assert err.value.status == 404
    assert queries.run_summary(db, run)["stage"] == "ENGINEER_REVIEW"


def test_only_assigned_approver_decides(db, run):
    """Scenario: 지정되지 않은 승인자 — 다른 승인자는 결정할 수 없다."""
    other = user(db, "다른 승인자", "APPROVER")
    db.commit()
    review.finish_review(db, run, approver(db), COMMENT)
    with pytest.raises(review.ReviewError) as err:
        review.decide(db, run, "APPROVED", None, other)
    assert err.value.status == 403 and "지정된 결재자" in str(err.value)
    assert queries.run_summary(db, run)["stage"] == "APPROVAL"
    assert review.decide(db, run, "APPROVED", "승인", approver(db))["stage"] == "APPROVED"


def test_withdraw_before_decision(db, run):
    """Scenario: 결정 전 취소 — 담당자 확인으로 돌아가고 다시 고칠 수 있으며 이력 1건이 남는다."""
    review.finish_review(db, run, approver(db), COMMENT)
    before = len(review.history(db, run))
    assert review.withdraw(db, run)["stage"] == "ENGINEER_REVIEW"
    log = review.history(db, run)
    assert len(log) == before + 1 and log[-1]["reason"] == "상신 취소"
    screen = review.approval(db, run)
    assert screen["stage"] == "ENGINEER_REVIEW" and screen["approval"] is None
    assert screen["preview"]                                # 다시 상신 전 확인이 보인다
    j = queries.run_judgments(db, run, limit=1)[0]
    review.act(RunContext(db, VERSION, None, None), run, "judgment", j["judgment_id"], "CONFIRM")
    again = review.finish_review(db, run, approver(db), "다시 올립니다")
    assert again["stage"] == "APPROVAL"
    assert review.approval(db, run)["approval"]["request_comment"] == "다시 올립니다"


def test_withdraw_after_approval(db, run):
    """Scenario: 승인된 뒤 취소 — 승인 대기에서만 취소할 수 있다."""
    review.finish_review(db, run, approver(db), COMMENT)
    review.decide(db, run, "APPROVED", "승인", approver(db))
    with pytest.raises(review.ReviewError) as err:
        review.withdraw(db, run)
    assert err.value.status == 409 and "승인 대기" in str(err.value)
    assert queries.run_summary(db, run)["stage"] == "APPROVED"


def test_review_sent_to_other_approver(db, run):
    """Scenario: 다른 결재자에게 간 검토 — 지정되지 않은 승인자의 내 할 일에는 보이지 않는다."""
    other = user(db, "다른 승인자", "APPROVER")
    db.commit()
    review.finish_review(db, run, approver(db), COMMENT)
    mine = [c for c in review.my_tasks(db, approver(db))["reviews"] if c["run_id"] == run]
    assert len(mine) == 1 and mine[0]["approval"]["request_comment"] == COMMENT
    assert [c for c in review.my_tasks(db, other)["reviews"] if c["run_id"] == run] == []


def test_approval_flow_api(db, run, db_url, monkeypatch):
    """결재 상신·상신 취소·결정 API의 오류 코드."""
    from fastapi.testclient import TestClient

    from rfp_agent.api.main import app
    from rfp_agent.config import get_settings

    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    get_settings.cache_clear()
    other = user(db, "다른 승인자", "APPROVER")
    db.commit()
    try:
        client = TestClient(app)
        url = f"/api/runs/{run}"
        assert client.post(f"{url}/finish-review", json={"approver_id": approver(db)}) \
            .status_code == 400
        assert client.post(f"{url}/finish-review", json={"comment": COMMENT}).status_code == 400
        assert client.post(f"{url}/finish-review",
                           json={"approver_id": 999999, "comment": COMMENT}).status_code == 404
        ok = client.post(f"{url}/finish-review",
                         json={"approver_id": approver(db), "comment": COMMENT})
        assert ok.status_code == 200 and ok.json()["stage"] == "APPROVAL"
        screen = client.get(f"{url}/approval").json()
        assert screen["approval"]["request_comment"] == COMMENT
        assert client.post(f"{url}/approval", json={"decision": "APPROVED",
                                                     "actor_id": other}).status_code == 403
        assert client.post(f"{url}/withdraw", json={}).json()["stage"] == "ENGINEER_REVIEW"
        assert client.post(f"{url}/withdraw", json={}).status_code == 409
    finally:
        get_settings.cache_clear()
