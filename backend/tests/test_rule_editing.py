"""판정 규칙 화면에서 규칙 고치기 (add-rule-editing). 명세 reference-data의 Scenario."""

import pytest
from docx import Document

from rfp_agent.db.seed import dict_version, seed_rules
from rfp_agent.pipeline import classify as cls
from rfp_agent.pipeline import reference, rule_edit
from rfp_agent.pipeline.docx_reader import read_blocks
from rfp_agent.pipeline.run import RunContext, create_run, execute_run
from tests.docx_factory import build_gis_spec, build_judgment_spec

SATISFACTION = "to the satisfaction of the Engineer"
NEW_RISK = {"expression": SATISFACTION, "language": "en", "risk_kind": "OPEN_SCOPE",
            "context_rule": "공급 범위 조항 안에 있을 때"}


def user(conn, role):
    return conn.execute("SELECT min(user_id) FROM app_user WHERE role = %s",
                        (role,)).fetchone()[0]


def satisfaction_spec(path):
    """공급 범위 절에 "to the satisfaction of the Engineer" 문장을 넣은 합성 사양서."""
    build_gis_spec(path)
    doc = Document(path)
    after = next(p for p in doc.paragraphs if p.text.startswith("3. CLARIFICATION"))
    after.insert_paragraph_before("All works shall be completed to the satisfaction of the "
                                  "Engineer.")
    doc.save(path)
    return path


def run_once(conn, settings, path):
    version = dict_version(settings.seed_dir, conn)
    run_id = create_run(conn, version, None)
    assert execute_run(RunContext(conn, version, None, None), run_id, [path]) == "ENGINEER_REVIEW"
    return run_id


def flags(conn, run_id, expression=SATISFACTION):
    return conn.execute(
        "SELECT count(*) FROM risk_flag f JOIN risk_expression e ON e.expr_id = f.expr_id "
        "WHERE f.run_id = %s AND e.expression = %s", (run_id, expression)).fetchone()[0]


def risk_row(conn, expression):
    return next((r for r in reference.risk_expressions(conn) if r["expression"] == expression),
                None)


def test_add_risk_expression(seeded_db, settings, tmp_path):
    """Scenario: 위험 표현 추가 — 사전에 줄이 생기고 다음 검토에서 위험 조건 후보가 된다."""
    path = satisfaction_spec(tmp_path / "synthetic_satisfaction.docx")
    before = run_once(seeded_db, settings, path)
    assert flags(seeded_db, before) == 0
    edit = rule_edit.add(seeded_db, "risk-expressions", NEW_RISK, "현업 멘토 사례",
                         user(seeded_db, "ENGINEER"))
    assert (edit["action"], edit["row_key"]) == ("ADD", {"expression": SATISFACTION})
    assert risk_row(seeded_db, SATISFACTION)["risk_kind"] == "OPEN_SCOPE"
    after = run_once(seeded_db, settings, path)
    assert flags(seeded_db, after) == 1


def test_edit_doc_kind_pattern(seeded_db, tmp_path):
    """Scenario: 문서 종류 표현 수정 — 다음 분류부터 "test spec" 파일이 시험 사양서가 된다."""
    path = build_judgment_spec(tmp_path / "GIS test spec rev2.docx")

    def kind():
        rules = cls.load_kind_rules(seeded_db)
        return cls.classify(path.name, read_blocks(path), [], rules).doc_kind

    assert kind() != "TEST_SPEC"
    row = next(r for r in reference.doc_kind_rules(seeded_db) if r["doc_kind"] == "TEST_SPEC")
    value = {**row, "name_pattern": "testing|시험|test spec"}
    rule_edit.update(seeded_db, "doc-kinds", str(row["doc_kind_rule_id"]), value,
                     "고객사 파일 이름", user(seeded_db, "ENGINEER"))
    assert kind() == "TEST_SPEC"


@pytest.mark.parametrize("change,reason,message", [
    ({"name_pattern": "testing|(시험"}, "사유", "파일 이름 표현: .*정규식이 아닙니다"),
    ({"doc_kind": "가격표"}, "사유", "문서 종류: '가격표'은\\(는\\) 코드표에 없습니다"),
    ({}, "  ", "사유: 고친 사유를 적어 주세요"),
])
def test_wrong_value_is_not_saved(seeded_db, change, reason, message):
    """Scenario: 틀린 값은 저장하지 않음 — 어느 칸이 왜 틀렸는지 알리고 사전·이력은 그대로."""
    row = next(r for r in reference.doc_kind_rules(seeded_db) if r["doc_kind"] == "TEST_SPEC")
    with pytest.raises(rule_edit.RuleEditError, match=message) as err:
        rule_edit.update(seeded_db, "doc-kinds", str(row["doc_kind_rule_id"]),
                         {**row, **change}, reason, user(seeded_db, "ENGINEER"))
    assert err.value.status == 400
    assert next(r for r in reference.doc_kind_rules(seeded_db)
                if r["doc_kind"] == "TEST_SPEC") == row
    assert rule_edit.edits(seeded_db) == []


def test_duplicate_key_is_not_saved(seeded_db):
    """이미 있는 키와 겹치면 저장하지 않는다 (409)."""
    with pytest.raises(rule_edit.RuleEditError, match="같은 키의 줄이 이미 있습니다") as err:
        rule_edit.add(seeded_db, "risk-expressions", {**NEW_RISK, "expression": "deemed"},
                      "겹침", user(seeded_db, "ENGINEER"))
    assert err.value.status == 409


def test_delete_risk_expression_used_by_old_run(seeded_db, settings, tmp_path):
    """Scenario: 지난 결과가 쓰는 위험 표현 삭제 — 목록·다음 검토에선 빠지고 지난 후보는 남는다."""
    path = build_gis_spec(tmp_path / "synthetic_154kV_GIS_spec.docx")
    expression = "including but not limited to"
    old = run_once(seeded_db, settings, path)
    n = flags(seeded_db, old, expression)
    assert n >= 1
    row = risk_row(seeded_db, expression)
    rule_edit.delete(seeded_db, "risk-expressions", str(row["expr_id"]), "너무 넓음",
                     user(seeded_db, "APPROVER"))
    assert risk_row(seeded_db, expression) is None
    assert flags(seeded_db, old, expression) == n          # 지난 후보는 그 표현과 함께 그대로
    new = run_once(seeded_db, settings, path)
    assert flags(seeded_db, new, expression) == 0


def test_delete_item_key_in_use(seeded_db):
    """Scenario: 쓰이는 표준 항목 삭제 — 지우지 않고 쓰는 곳을 알린다."""
    with pytest.raises(rule_edit.RuleEditError, match="rated_current을\\(를\\) 쓰는 곳이 있어 "
                       "지울 수 없습니다: 비교 방향 규칙 \\d+줄, 제품표 연결 1줄") as err:
        rule_edit.delete(seeded_db, "items", "rated_current", "안 씀",
                         user(seeded_db, "ENGINEER"))
    assert err.value.status == 409
    assert any(r["item_key"] == "rated_current" for r in reference.items(seeded_db))


def test_other_role_cannot_edit(seeded_db):
    """Scenario: 권한 없는 사람 — 견적 담당은 저장하지 않고 엔지니어·승인자만 된다고 알린다."""
    with pytest.raises(rule_edit.RuleEditError, match="엔지니어·승인자만") as err:
        rule_edit.add(seeded_db, "risk-expressions", NEW_RISK, "추가", user(seeded_db, "COST"))
    assert err.value.status == 403
    assert risk_row(seeded_db, SATISFACTION) is None


def test_edit_history(seeded_db):
    """Scenario: 고침 이력 보기 — 수정 전·후 값, 사유, 고친 사람, 시각."""
    engineer = user(seeded_db, "ENGINEER")
    row = risk_row(seeded_db, "deemed")
    value = {k: row[k] for k in ("expression", "language", "risk_kind", "context_rule")}
    rule_edit.update(seeded_db, "risk-expressions", str(row["expr_id"]),
                     {**value, "context_rule": "계약 조항 안에서만"}, "조건 좁힘", engineer)
    [edit] = rule_edit.edits(seeded_db, "risk-expressions")
    assert edit["action"] == "EDIT" and edit["row_key"] == {"expression": "deemed"}
    assert edit["before_value"] == value
    assert edit["after_value"] == {**value, "context_rule": "계약 조항 안에서만"}
    assert (edit["reason"], edit["actor_id"], edit["actor_name"]) == ("조건 좁힘", engineer,
                                                                      "기본 엔지니어")
    assert edit["edited_at"] is not None and edit["discarded_at"] is None


def test_new_version_after_edit(seeded_db, settings, tmp_path):
    """Scenario: 고친 뒤 다시 검토 — 두 검토의 판이 다르고 첫 검토의 후보 수는 그대로다."""
    path = satisfaction_spec(tmp_path / "synthetic_satisfaction.docx")
    first = run_once(seeded_db, settings, path)
    count = seeded_db.execute("SELECT count(*) FROM risk_flag WHERE run_id = %s",
                              (first,)).fetchone()[0]
    rule_edit.add(seeded_db, "risk-expressions", NEW_RISK, "추가", user(seeded_db, "ENGINEER"))
    second = run_once(seeded_db, settings, path)
    v1, v2 = (seeded_db.execute("SELECT dict_version FROM review_run WHERE run_id = %s",
                                (r,)).fetchone()[0] for r in (first, second))
    assert v1 != v2 and v2.endswith("+e1")
    assert seeded_db.execute("SELECT count(*) FROM risk_flag WHERE run_id = %s",
                             (first,)).fetchone()[0] == count
    assert flags(seeded_db, second) == 1


def test_reseed_keeps_edits(seeded_db, settings):
    """Scenario: 다시 적재해도 고침이 남음 — 그 표현이 그대로 있고 사전 판도 같다."""
    engineer = user(seeded_db, "ENGINEER")
    rule_edit.add(seeded_db, "risk-expressions", NEW_RISK, "추가", engineer)
    item = next(r for r in reference.items(seeded_db) if r["item_key"] == "rated_current")
    rule_edit.update(seeded_db, "items", "rated_current",
                     {**item, "aliases": [*item["aliases"], "Continuous current rating"]},
                     "표현 추가", engineer)
    version = dict_version(settings.seed_dir, seeded_db)
    report = seed_rules(seeded_db, settings.seed_dir)
    assert report.counts["다시 적용한 규칙 고침"] == 2 and not [
        s for s in report.skipped if s.startswith("규칙 고침")]
    assert risk_row(seeded_db, SATISFACTION)["risk_kind"] == "OPEN_SCOPE"
    item = next(r for r in reference.items(seeded_db) if r["item_key"] == "rated_current")
    assert "Continuous current rating" in item["aliases"]
    assert dict_version(settings.seed_dir, seeded_db) == version


def test_reseed_skips_edit_it_cannot_apply(seeded_db, settings):
    """다시 적용할 수 없는 고침(그 줄이 사라짐)은 건너뛰고 알린다."""
    row = risk_row(seeded_db, "deemed")
    value = {k: row[k] for k in ("expression", "language", "risk_kind", "context_rule")}
    rule_edit.update(seeded_db, "risk-expressions", str(row["expr_id"]),
                     {**value, "context_rule": "x"}, "수정", user(seeded_db, "ENGINEER"))
    seeded_db.execute("UPDATE rule_edit SET row_key = '{\"expression\": \"gone\"}'")
    report = seed_rules(seeded_db, settings.seed_dir)
    assert report.counts["다시 적용한 규칙 고침"] == 0
    assert any("규칙 고침 1 (위험 표현 gone)" in s for s in report.skipped)


def test_reseed_discarding_edits(seeded_db, settings):
    """Scenario: 고침 버리기 — 사전은 파일 내용만 남고, 이력은 "버림"으로 남는다."""
    csv_version = dict_version(settings.seed_dir)
    rule_edit.add(seeded_db, "risk-expressions", NEW_RISK, "추가", user(seeded_db, "ENGINEER"))
    report = seed_rules(seeded_db, settings.seed_dir, reset_edits=True)
    assert report.counts["버린 규칙 고침"] == 1
    assert risk_row(seeded_db, SATISFACTION) is None
    [edit] = rule_edit.edits(seeded_db)
    assert edit["discarded_at"] is not None
    assert dict_version(settings.seed_dir, seeded_db) == csv_version


def test_rule_edit_api(seeded_db, db_url, monkeypatch):
    """고치기 API: 추가 201, 수정, 삭제(본문에 사유), 이력, 권한 403, 검사 400."""
    from fastapi.testclient import TestClient

    from rfp_agent.api.main import app
    from rfp_agent.config import get_settings

    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    try:
        client = TestClient(app)
        engineer, cost = user(seeded_db, "ENGINEER"), user(seeded_db, "COST")
        body = {"value": NEW_RISK, "reason": "추가", "actor_id": engineer}
        assert client.post("/api/rules/risk-expressions", json=body).status_code == 201
        row = next(r for r in client.get("/api/rules/risk-expressions").json()
                   if r["expression"] == SATISFACTION)
        url = f"/api/rules/risk-expressions/{row['expr_id']}"
        put = client.put(url, json={**body, "value": {**NEW_RISK, "risk_kind": "BLANKET"},
                                    "reason": "종류"})
        assert put.status_code == 200 and put.json()["after_value"]["risk_kind"] == "BLANKET"
        assert client.request("DELETE", url, json={"reason": "삭제", "actor_id": cost}
                              ).status_code == 403
        assert client.request("DELETE", url, json={"reason": "삭제", "actor_id": engineer}
                              ).status_code == 200
        wrong = {**body, "value": {**NEW_RISK, "risk_kind": "X"}}
        assert client.post("/api/rules/risk-expressions", json=wrong).status_code == 400
        history = client.get("/api/rules/edits", params={"dictionary": "risk-expressions"}).json()
        assert [e["action"] for e in history] == ["DELETE", "EDIT", "ADD"]
        assert client.get("/api/rules/edits", params={"dictionary": "x"}).status_code == 422
    finally:
        get_settings.cache_clear()
