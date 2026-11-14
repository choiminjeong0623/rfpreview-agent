"""FR-04 유형 표시 (명세 requirement-extraction)."""

import csv

import pytest

from rfp_agent.config import get_settings
from rfp_agent.pipeline.extract import Candidate
from rfp_agent.pipeline.type_tags import TypeRule, tag


@pytest.fixture(scope="module")
def rules():
    with open(get_settings().seed_dir / "type_rules.csv", encoding="utf-8-sig") as f:
        return [TypeRule(None, r["rule_code"], r["pattern"], r["type_code"], r["match_kind"],
                         int(r["priority"])) for r in csv.DictReader(f)]


def primary(text, rules):
    cand = Candidate(block=None, source_kind="TABLE_CELL", text=text, req_kind="REQUIREMENT",
                     rule_id="E-TABLE-ROW", section=None)
    tags = tag(cand, rules, [])
    return next(t.type_code for t in tags if t.is_primary), [t.type_code for t in tags]


def test_test_report(rules):
    """Scenario: 시험."""
    assert primary("Type Test Report / Required", rules)[0] == "TEST"


def test_maker_qualification(rules):
    """Scenario: 제조사 자격."""
    assert primary("ISO 9001 or equivalent certificates / Required", rules)[0] == "MAKER_QUAL"


def test_loss_clause_is_cost_then_performance(rules):
    text = ("In the bid evaluation procedure, each loss evaluation figure listed below will be "
            "multiplied by its guaranteed loss value and added to give a total evaluated price.")
    first, tags = primary(text, rules)
    assert first == "COST" and "TECH_PERF" in tags
