"""유형 규칙 빈틈 채우기 (change update-type-rule-gaps).

명세 requirement-extraction "보강한 유형 규칙"의 Scenario.
규칙은 기준 데이터(type_rules.csv)에서 읽는다.
"""

import pytest

from rfp_agent.pipeline import dictionaries
from rfp_agent.pipeline.extract import Candidate
from rfp_agent.pipeline.type_tags import tag


@pytest.fixture
def primary(db):
    dicts = dictionaries.load(db)
    risk = [e.pattern for e in dicts.risk_expressions]

    def first(text: str) -> str:
        cand = Candidate(block=None, source_kind="SENTENCE", text=text, req_kind="REQUIREMENT",
                         rule_id="E-SENTENCE-MARKER", section=None)
        tags = tag(cand, dicts.type_rules, risk)
        return tags[0].type_code if tags else "NONE"
    return first


def test_standards_without_number(primary):
    """Scenario: 번호 없는 규격 이름 — 적용 규격·인증."""
    assert primary("Applicable IEC/ANSI/UL standards, declarations, certificates, and test "
                   "reports.") == "STANDARD_CERT"


def test_rated_line_with_standards(primary):
    """Scenario: 기술 성능 줄의 규격 이름 — 기술 성능이 그대로 주 유형."""
    assert primary("Rated terminal load / As per IEC standards") == "TECH_PERF"


def test_unit_price(db, primary):
    """Scenario: 단가 조건 — 비용 영향, 견적 담당 협조 요청 대상."""
    assert primary("Commercial proposal showing unit price, quantity, delivery term, warranty, "
                   "and validity period.") == "COST"
    role = db.execute("SELECT default_role FROM requirement_type WHERE type_code = 'COST'")
    assert role.fetchone()[0] == "COST"


def test_korean_typo_unit_price(primary):
    """Scenario: 한국어 오타의 단가 — "차단가"는 단가 규칙으로 비용 영향이 되지 않음."""
    assert primary("차단가의 보조접점은 10,000회 연속 개폐 후에도 성능을 유지하여야 한다") != "COST"
    assert primary("각 부품별 단가를 오너의 승인을 받아 제출하여야 한다") == "COST"


def test_manufacturer_authorization(primary):
    """Scenario: 제조사 위임 — 제조사 자격."""
    assert primary("Manufacturer authorization, production facility information, after-sales "
                   "organization, and technical support plan.") == "MAKER_QUAL"


def test_gas_leakage(primary):
    """Scenario: 가스 누설 — 기술 성능."""
    assert primary("The annual gas leakage rate of each gas compartment of the GIS shall not "
                   "exceed 0.5 %.") == "TECH_PERF"
