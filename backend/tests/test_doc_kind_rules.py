"""문서 종류 규칙 사전 (적재, 분류, 조회).

명세 document-intake·reference-data(update-doc-kind-rules)의 Scenario.
"""

import shutil

import pytest

from rfp_agent.db.migrate import migrate
from rfp_agent.db.seed import SeedError, seed_rules
from rfp_agent.pipeline import classify as cls
from rfp_agent.pipeline import reference
from rfp_agent.pipeline.docx_reader import read_blocks
from rfp_agent.pipeline.run import RunContext, create_run, execute_run
from tests.docx_factory import build_judgment_spec


def kinds(conn):
    return [(r["priority"], r["doc_kind"]) for r in reference.doc_kind_rules(conn)]


def classify(conn, path):
    return cls.classify(path.name, read_blocks(path), [], cls.load_kind_rules(conn))


def test_rules_decide_kind_in_order(seeded_db, tmp_path):
    """Scenario: 사전 순서대로 문서 종류 정하기 — 사전 순서대로 문서 종류 정하기"""
    path = build_judgment_spec(tmp_path / "Testing Specification.docx")
    c = classify(seeded_db, path)
    assert (c.doc_kind, c.rule_id) == ("TEST_SPEC", "K-NAME-TEST_SPEC")


def test_no_rule_matches(seeded_db, tmp_path):
    """Scenario: 사전에 없는 표현 — 사전에 없는 표현"""
    c = classify(seeded_db, build_judgment_spec(tmp_path / "datasheet_x.docx"))
    assert (c.doc_kind, c.rule_id, c.needs_review) == ("UNKNOWN", "K-NONE", True)


def test_first_page_rule(seeded_db, tmp_path):
    path = build_judgment_spec(tmp_path / "attachment_7.docx", "PURCHASE REQUISITION FOR GIS")
    assert classify(seeded_db, path).rule_id == "K-PAGE-PURCHASE_SPEC"


def test_doc_kind_rules_seed_twice(empty_db, settings):
    """Scenario: 문서 종류 규칙 두 번 적재 — 문서 종류 규칙 두 번 적재"""
    migrate(empty_db, settings.migrations_dir)
    expected = [(1, "BID_FORM"), (2, "SUPPLIER_SPEC"), (3, "TEST_SPEC"), (4, "PURCHASE_SPEC"),
                (5, "REQUIREMENT_SPEC"), (6, "BOQ"), (7, "REQUIREMENT_SPEC")]
    for _ in range(2):
        assert seed_rules(empty_db, settings.seed_dir).counts["doc_kind_rule"] == 7
        assert kinds(empty_db) == expected


@pytest.mark.parametrize("old,new,message", [
    (",TEST_SPEC,", ",가격표,", "문서 종류 '가격표'"),
    ("testing|시험", "testing|(시험", "정규식이 아님"),
])
def test_unknown_doc_kind_stops_seed(empty_db, settings, tmp_path, old, new, message):
    """Scenario: 모르는 문서 종류 — 모르는 문서 종류 (정규식이 아닌 표현도 같다)"""
    migrate(empty_db, settings.migrations_dir)
    seed_dir = tmp_path / "seed"
    shutil.copytree(settings.seed_dir, seed_dir)
    rules = seed_dir / "doc_kind_rules.csv"
    rules.write_text(rules.read_text(encoding="utf-8").replace(old, new, 1), encoding="utf-8")
    with pytest.raises(SeedError, match=f"문서 종류 규칙 4행: .*{message}"):
        seed_rules(empty_db, seed_dir)
    assert empty_db.execute("SELECT count(*) FROM doc_kind_rule").fetchone()[0] == 0
    assert empty_db.execute("SELECT count(*) FROM item_key").fetchone()[0] == 0


def test_doc_kind_rules_view(seeded_db, tmp_path):
    """Scenario: 문서 종류 규칙 보기 — 문서 종류 규칙 보기"""
    path = build_judgment_spec(tmp_path / "1. Bidding Forms_synthetic.docx")
    run_id = create_run(seeded_db, "v", None)
    assert execute_run(RunContext(seeded_db, "v", None, None), run_id, [path]) == "ENGINEER_REVIEW"
    rows = reference.doc_kind_rules(seeded_db)
    assert [r["priority"] for r in rows] == [1, 2, 3, 4, 5, 6, 7]
    bid = rows[0]
    assert (bid["doc_kind"], bid["name_pattern"], bid["used"]) == ("BID_FORM", "bidding forms", 1)
    assert all(r["used"] == 0 for r in rows[1:])
