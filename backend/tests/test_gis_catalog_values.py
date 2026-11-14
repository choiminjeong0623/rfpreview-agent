"""GIS 제품 카탈로그 정격값 (change update-gis-catalog-values).

명세 reference-data "GIS 카탈로그 정격값"의 Scenario. 고정 제품표(fixtures)가 아니라 실제 제품표
(data/seed/products/product_master.csv)를 적재해 본다.
"""

import pytest

from rfp_agent.db.migrate import migrate
from rfp_agent.db.seed import seed_products
from rfp_agent.pipeline.compare import ReqValue, compare
from rfp_agent.pipeline.products import load_products, product_value


@pytest.fixture
def real_products(empty_db, settings):
    migrate(empty_db, settings.migrations_dir)
    seed_products(empty_db, [settings.seed_dir / "products" / "product_master.csv"])
    return {p.code: p for p in load_products(empty_db)}


def test_real_master_gis_ratings(real_products):
    """Scenario: 실제 제품표의 GIS 정격값 — 정격 전류·단시간 전류 시간, 팀 가정 아님."""
    expected = {"GIS-145-40": (3150, 3), "GIS-245-40": (3150, 3), "GIS-245-50": (3150, 3),
                "GIS-170-50": (4000, 1)}
    for code, (amps, seconds) in expected.items():
        p = real_products[code]
        current = product_value(p, "rated_current", "rated_current_a")
        assert (current.num, current.unit) == (amps, "A"), code
        assert p.short_time_s == seconds, code
        assert not p.value_assumed("rated_current_a"), code
        assert "카탈로그" in p.description, code                      # 출처 쪽수를 함께 남김


def test_rated_current_requirement_against_real_gis(real_products):
    """Scenario: 정격 전류 요구 판정 — "3150 A 이상"과 GIS-170-50은 준수, 제품값 4000 A."""
    prod = product_value(real_products["GIS-170-50"], "rated_current", "rated_current_a")
    req = ReqValue(raw="≥3150", cell_form="NUMBER", num=3150, operator=">=", unit="A",
                   time_s=None, item_key="rated_current", basis_standard=None, flag=None)
    verdict = compare(req, prod, "GE", "HIGHER")
    assert verdict.result == "COMPLY"
    assert prod.raw.replace(",", "").startswith("4000")
