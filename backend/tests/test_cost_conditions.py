"""FR-16 비용 조건 요약 (add-cost-conditions). 명세 cost-conditions의 Scenario."""

import csv

import pytest
from docx import Document

from rfp_agent.config import get_settings
from rfp_agent.pipeline import review
from rfp_agent.pipeline.cost_conditions import cost_conditions, cost_summary, kind_of
from rfp_agent.pipeline.extract import Candidate
from rfp_agent.pipeline.run import RunContext, create_run, execute_run
from rfp_agent.pipeline.type_tags import TypeRule, tag
from tests.docx_factory import build_judgment_spec, build_loss_spec

VERSION = "test-dict-v1"
LD = "Liquidated damages shall be 0.5 % of the Contract Price per week of delay."
WITNESS = "Type Test shall be witnessed by the Employer."
DEFECT_1 = "The Defects Notification Period shall be 24 months from Taking-Over."
DEFECT_2 = "The warranty period for spare parts shall be 12 months after delivery."
TOOLS = "Special tools shall be supplied at no additional cost."
LIABILITY = "The Contractor's total liability shall not be limited."
C_DEFECT = "The Defects Liability Period of the switchgear shall be 36 months."


@pytest.fixture(scope="module")
def rules():
    with open(get_settings().seed_dir / "type_rules.csv", encoding="utf-8-sig") as f:
        return [TypeRule(None, r["rule_code"], r["pattern"], r["type_code"], r["match_kind"],
                         int(r["priority"])) for r in csv.DictReader(f)]


def tags_of(text, rules):
    cand = Candidate(block=None, source_kind="SENTENCE", text=text, req_kind="REQUIREMENT",
                     rule_id="E-SHALL", section=None)
    found = tag(cand, rules, [])
    return {t.type_code: t for t in found}, next(t for t in found if t.is_primary)


def build_cost_spec(path):
    """판정 데이터시트 + 상업 조항 문장."""
    build_judgment_spec(path)
    doc = Document(str(path))
    doc.add_paragraph("3. COMMERCIAL CONDITIONS")
    for text in (LD, WITNESS, DEFECT_1, DEFECT_2, TOOLS, LIABILITY):
        doc.add_paragraph(text)
    doc.save(str(path))
    return path


def build_c_doc(path):
    doc = Document()
    doc.add_paragraph("EMPLOYER'S REQUIREMENTS")
    doc.add_paragraph("1. GENERAL")
    doc.add_paragraph("The works shall be as specified in the general specification.")
    doc.add_paragraph("2. WARRANTY")
    doc.add_paragraph(C_DEFECT)
    for no, topic in enumerate(("PAINTING", "EARTHING", "NAMEPLATES", "CABLING"), start=3):
        doc.add_paragraph(f"{no}. {topic}")                  # 읽을 수 있는 문서는 10줄 이상
        doc.add_paragraph(f"The {topic.lower()} shall be as specified in the specification.")
    doc.save(str(path))
    return path


@pytest.fixture
def cost_run(db, tmp_path):
    main = build_cost_spec(tmp_path / "synthetic_judgment_cost.docx")
    other = build_c_doc(tmp_path / "synthetic_general_conditions.docx")
    run_id = create_run(db, VERSION, None)
    choices = {other.name: {"bundle": "C"}}
    assert execute_run(RunContext(db, VERSION, None, None), run_id, [main, other],
                       choices) == "ENGINEER_REVIEW"
    return db, run_id


def by_text(rows, text):
    return next(r for r in rows if r["text"] == text)


def test_liquidated_damages_rule(rules):
    """Scenario: 지체상금 문장 — 주 유형은 비용 영향, 근거는 지체상금 규칙."""
    found, first = tags_of(LD, rules)
    assert first.type_code == "COST" and first.rule.rule_code == "T-COST-05"
    assert kind_of(LD) == "지체상금"


def test_witness_is_secondary_cost(rules):
    """Scenario: 시험 입회 문장 — 주 유형은 시험, 보조 유형은 비용 영향."""
    found, first = tags_of(WITNESS, rules)
    assert first.type_code == "TEST" and not found["COST"].is_primary
    assert kind_of(WITNESS) == "시험 입회"


def test_new_rules_keep_test_and_qualification_primary(rules):
    """새 비용 규칙은 시험·제조사 자격 줄의 주 유형을 바꾸지 않는다 (우선순위 25)."""
    assert tags_of("Type Test Report shall be submitted with packing list.", rules)[1].type_code \
        == "TEST"
    assert tags_of("The manufacturer shall have experience in training.", rules)[1].type_code \
        == "MAKER_QUAL"


def test_grouped_by_kind(cost_run):
    """Scenario: 종류별로 묶기 — 지체상금 1건, 하자 보증 2건이 원문 위치와 함께."""
    conn, run_id = cost_run
    rows = cost_conditions(conn, run_id)
    kinds = [r["kind"] for r in rows]
    assert kinds.count("지체상금") == 1 and kinds.count("하자 보증") == 3   # 묶음 C 문서 1건 포함
    assert all(r["locations"] for r in rows)
    assert kinds == sorted(kinds, key=lambda k: [
        "지체상금", "책임 한도", "하자 보증", "이행 보증서", "지급 조건", "가격 유효 기간",
        "인도 조건", "통화·환율", "손실 평가", "예비품", "특수 공구", "운반·포장", "시험 입회",
        "설치 감독", "교육", "무상 공급", "기타 비용"].index(k))


def test_values_kept_as_written(cost_run):
    """Scenario: 값은 원문 그대로 — "24 months"가 그대로 보이고 바뀐 단위는 없다."""
    conn, run_id = cost_run
    row = by_text(cost_conditions(conn, run_id), DEFECT_1)
    assert any("24" in v for v in row["values"])
    assert not any("year" in v or "day" in v for v in row["values"])


def test_contractor_burden(cost_run):
    """Scenario: 계약상대자 부담 표시 — 특수 공구 종류, "계약상대자 부담"."""
    conn, run_id = cost_run
    row = by_text(cost_conditions(conn, run_id), TOOLS)
    assert row["kind"] == "특수 공구" and row["burden"] == "계약상대자 부담"


def test_unlimited_liability(cost_run):
    """Scenario: 책임 한도 없음 표시 — 책임 한도 종류, 위험 표시."""
    conn, run_id = cost_run
    row = by_text(cost_conditions(conn, run_id), LIABILITY)
    assert row["kind"] == "책임 한도" and row["risk"] == "책임 한도 없음"


def test_bundle_c_included(cost_run):
    """Scenario: 묶음 C 문서도 포함 — 묶음 C 문서의 하자 보증 기간 줄도 있다."""
    conn, run_id = cost_run
    row = by_text(cost_conditions(conn, run_id), C_DEFECT)
    assert row["kind"] == "하자 보증" and row["file_name"] == "synthetic_general_conditions.docx"


def test_request_status(cost_run):
    """Scenario: 협조 요청 상태 — 지체상금은 견적 협조 요청 상태, 시험 입회는 협조 요청 없음."""
    conn, run_id = cost_run
    rows = cost_conditions(conn, run_id)
    ld = by_text(rows, LD)
    assert ld["primary_type"] == "COST" and ld["request_status"] == "TODO"
    assert ld["assignment_id"] is not None
    witness = by_text(rows, WITNESS)
    assert witness["primary_type"] == "TEST" and witness["request_status"] is None
    [task] = [t for t in review.assignments_for(conn, "COST", run_id)
              if t["requirement_id"] == ld["requirement_id"]]
    assert task["assignment_id"] == ld["assignment_id"]


def test_without_location_left_out(cost_run):
    """Scenario: 원문 위치 없는 줄 — 비용 조건에 없다 (CR-02)."""
    conn, run_id = cost_run
    ld = by_text(cost_conditions(conn, run_id), LD)
    conn.execute("DELETE FROM requirement_location WHERE requirement_id = %s",
                 (ld["requirement_id"],))
    conn.commit()
    assert LD not in [r["text"] for r in cost_conditions(conn, run_id)]


def test_loss_amount_with_team_assumption(db, tmp_path):
    """Scenario: 손실 환산 가산액 — 팀 가정 표시가 있는 가산액 줄 1건 (새로 계산하지 않음)."""
    from rfp_agent.pipeline.loss import recalculate

    path = build_loss_spec(tmp_path / "synthetic_judgment_loss.docx")
    run_id = create_run(db, VERSION, None)
    assert execute_run(RunContext(db, VERSION, None, None), run_id, [path]) == "ENGINEER_REVIEW"
    [loss_id] = [r[0] for r in db.execute("SELECT loss_calc_id FROM loss_calc WHERE run_id = %s",
                                          (run_id,))]
    recalculate(db, loss_id, 60, 300, 8)
    db.commit()
    [impact] = [i for i in cost_summary(db, run_id)["impacts"] if i["kind"] == "LOSS"]
    total = db.execute("SELECT total_usd FROM loss_calc WHERE loss_calc_id = %s",
                       (loss_id,)).fetchone()[0]
    assert impact["is_assumed"] and impact["total_usd"] == float(total)


def test_deviation_impact(cost_run):
    """Scenario: 일탈 후보 가격 영향 — 뺀 일탈은 빠지고 남은 것마다 한 줄."""
    conn, run_id = cost_run
    items = [r[0] for r in conn.execute(
        "SELECT item_id FROM output_item WHERE run_id = %s AND list_kind = 'DEVIATION' "
        "ORDER BY item_id", (run_id,))]
    assert items, "합성 판정 문서에는 일탈 후보가 있어야 한다"
    conn.execute("UPDATE output_item SET status = 'REMOVED' WHERE item_id = %s", (items[0],))
    conn.commit()
    impacts = [i for i in cost_summary(conn, run_id)["impacts"] if i["kind"] == "DEVIATION"]
    assert [i["item_id"] for i in impacts] == items[1:]
    assert all(i["judgment_id"] and i["locations"] for i in impacts)


def test_cost_conditions_api(cost_run, db_url, monkeypatch):
    """상업 조건 API: 응답 모델대로 비용 조건과 상업 영향을 준다."""
    from fastapi.testclient import TestClient

    from rfp_agent.api.main import app

    conn, run_id = cost_run
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    get_settings.cache_clear()
    try:
        res = TestClient(app).get(f"/api/runs/{run_id}/cost-conditions")
        assert res.status_code == 200
        body = res.json()
        assert by_text(body["conditions"], LD)["kind"] == "지체상금"
        assert TestClient(app).get("/api/runs/999999/cost-conditions").status_code == 404
    finally:
        get_settings.cache_clear()
