"""실행 목록의 결재 정보 (change update-review-list-approval, 명세 review-run)."""

import pytest

from rfp_agent.pipeline import queries, review
from rfp_agent.pipeline.run import RunContext, create_run, execute_run

VERSION = "test-dict-v1"
COMMENT = "질의 1건은 회신 예정"


@pytest.fixture
def run(db, spec):
    run_id = create_run(db, VERSION, None)
    assert execute_run(RunContext(db, VERSION, None, None), run_id, [spec]) == "ENGINEER_REVIEW"
    return run_id


def row(db, run_id):
    return next(r for r in queries.run_list(db) if r["run_id"] == run_id)


APPROVAL_FIELDS = ("approver_id", "approver", "requested_by_id", "requested_by", "requested_at",
                   "decision", "decided_at")


def test_list_has_latest_approval(db, run):
    """Scenario: 상신한 검토의 결재 정보."""
    assert all(row(db, run)[k] is None for k in APPROVAL_FIELDS)     # 상신 전
    engineer = review.default_user(db, "ENGINEER")
    approver = review.default_user(db, "APPROVER")
    review.finish_review(db, run, approver, COMMENT, engineer)
    r = row(db, run)
    assert (r["approver_id"], r["approver"]) == (approver, "기본 승인자")
    assert (r["requested_by_id"], r["requested_by"]) == (engineer, "기본 엔지니어")
    assert r["requested_at"] is not None
    assert r["decision"] is None and r["decided_at"] is None


def test_withdrawn_approval_is_empty(db, run):
    """Scenario: 취소한 상신."""
    engineer = review.default_user(db, "ENGINEER")
    review.finish_review(db, run, review.default_user(db, "APPROVER"), COMMENT, engineer)
    review.withdraw(db, run, engineer)
    assert all(row(db, run)[k] is None for k in APPROVAL_FIELDS)


def test_rejected_approval(db, run):
    """Scenario: 반려된 검토 — 다시 상신하지 않았으면 결정은 반려, 결정 시각이 있다."""
    engineer = review.default_user(db, "ENGINEER")
    approver = review.default_user(db, "APPROVER")
    review.finish_review(db, run, approver, COMMENT, engineer)
    review.decide(db, run, "REJECTED", "질의 문장 다시", approver)
    r = row(db, run)
    assert r["decision"] == "REJECTED" and r["decided_at"] is not None
    assert r["requested_by_id"] == engineer


def test_list_api_has_approval_fields(client_for_list, run):
    """API 응답에도 결재 칸이 있다(응답 스키마)."""
    body = client_for_list.get("/api/runs").json()
    item = next(i for i in body if i["run_id"] == run)
    assert set(APPROVAL_FIELDS) <= set(item)


@pytest.fixture
def client_for_list(db, db_url, monkeypatch):
    from fastapi.testclient import TestClient

    from rfp_agent.api.main import app
    from rfp_agent.config import get_settings

    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    yield TestClient(app)
    get_settings.cache_clear()
