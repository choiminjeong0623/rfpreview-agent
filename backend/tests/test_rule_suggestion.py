"""위험 표현 사전에 추가 제안 (change add-rule-suggestion, 명세 risk-detection)."""

import pytest

from rfp_agent.pipeline import rule_suggestion as rs
from rfp_agent.pipeline.review import ReviewError
from rfp_agent.pipeline.run import RunContext, create_run, execute_run
from tests.docx_factory import build_gis_spec

VERSION = "test-dict-v1"
PHRASE = "corresponding to the Employer's Requirement"


@pytest.fixture
def run(db, spec, tmp_path):
    gis = build_gis_spec(tmp_path / "synthetic_154kV_GIS_spec.docx")
    run_id = create_run(db, VERSION, None)
    assert execute_run(RunContext(db, VERSION, None, None), run_id, [gis, spec]) == \
        "ENGINEER_REVIEW"
    return run_id


def user(db, role):
    return db.execute("SELECT min(user_id) FROM app_user WHERE role = %s", (role,)).fetchone()[0]


def expressions(db):
    return [r[0] for r in db.execute("SELECT expression FROM risk_expression WHERE active")]


def test_suggest_found_in_document(db, run):
    """Scenario: 문서에 있는 표현 제안 — 확인 대기 1건, 원문 위치, 사전은 그대로."""
    before = expressions(db)
    s = rs.suggest(db, run, "  " + PHRASE.upper() + " ", "표준 사양에 없는 요구")
    assert s["status"] == "PENDING" and s["expression"] == PHRASE.upper()
    text = db.execute("SELECT text_raw FROM requirement WHERE requirement_id = %s",
                      (s["requirement_id"],)).fetchone()[0]
    assert PHRASE in text
    assert s["locations"] and s["note"] == "표준 사양에 없는 요구"
    assert [x["suggestion_id"] for x in rs.listing(db, run)] == [s["suggestion_id"]]
    assert expressions(db) == before


def test_not_in_document(db, run):
    """Scenario: 문서에 없는 표현."""
    with pytest.raises(ReviewError, match="이 검토 문서에서 찾지 못했습니다"):
        rs.suggest(db, run, "to the satisfaction of the Engineer")
    assert rs.listing(db, run) == []


def test_already_known(db, run):
    """Scenario: 이미 있는 표현 — 사전에 있거나 확인 대기 중이면 받지 않는다."""
    with pytest.raises(ReviewError) as e:
        rs.suggest(db, run, "Deemed")
    assert e.value.status == 409
    rs.suggest(db, run, PHRASE)
    with pytest.raises(ReviewError) as e:
        rs.suggest(db, run, PHRASE.lower())
    assert e.value.status == 409


def test_accept(db, run):
    """Scenario: 제안 반영 — 사전에 1줄, 고침 이력 1건, 상태 반영."""
    s = rs.suggest(db, run, PHRASE)
    edits = db.execute("SELECT count(*) FROM rule_edit").fetchone()[0]
    done = rs.accept(db, s["suggestion_id"],
                     {"language": "en", "risk_kind": "BLANKET", "context_rule": ""},
                     "검토 제안 반영", user(db, "APPROVER"))
    assert done["status"] == "ACCEPTED" and done["edit_id"]
    assert done["decided_by"] == user(db, "APPROVER")
    assert expressions(db).count(PHRASE) == 1
    assert db.execute("SELECT count(*) FROM rule_edit").fetchone()[0] == edits + 1
    with pytest.raises(ReviewError) as e:          # 이미 결정한 제안
        rs.decline(db, s["suggestion_id"], "다시", user(db, "ENGINEER"))
    assert e.value.status == 409


def test_decline(db, run):
    """Scenario: 제안 반려 — 상태 반려, 사유, 사전 그대로."""
    s = rs.suggest(db, run, PHRASE)
    before = expressions(db)
    with pytest.raises(ReviewError):
        rs.decline(db, s["suggestion_id"], " ", user(db, "ENGINEER"))
    done = rs.decline(db, s["suggestion_id"], "일반 문구라 위험 아님", user(db, "ENGINEER"))
    assert done["status"] == "DECLINED" and done["decision_reason"] == "일반 문구라 위험 아님"
    assert expressions(db) == before
    rs.suggest(db, run, PHRASE)                     # 반려한 표현은 다시 제안할 수 있다


def test_no_permission(db, run):
    """Scenario: 권한 없음 — 영업 역할은 반영할 수 없다."""
    s = rs.suggest(db, run, PHRASE)
    with pytest.raises(ReviewError) as e:
        rs.accept(db, s["suggestion_id"], {"language": "en", "risk_kind": "BLANKET"}, "반영",
                  user(db, "SALES"))
    assert e.value.status == 403
    assert rs.listing(db, run)[0]["status"] == "PENDING"


def test_bad_rule_value_keeps_pending(db, run):
    """사전 값이 틀리면(종류 없음) 반영하지 않고 확인 대기 그대로."""
    s = rs.suggest(db, run, PHRASE)
    with pytest.raises(ReviewError) as e:
        rs.accept(db, s["suggestion_id"], {"language": "en"}, "반영", user(db, "ENGINEER"))
    assert e.value.status == 400
    assert rs.listing(db, run)[0]["status"] == "PENDING"
    assert PHRASE not in expressions(db)
