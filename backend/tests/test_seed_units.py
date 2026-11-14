import pytest

from rfp_agent.db.seed import SeedError, direction_code, product_row, table_name_of


@pytest.mark.parametrize(
    ("text", "code"),
    [("≥ (+시간)", "GE"), ("<", "LT"), ("작성", "FILL"), ("< / ≤ / >", "SOURCE")],
)
def test_direction_code(text, code):
    """Scenario: 시간 조건이 붙은 비교 방향."""
    assert direction_code(text, "test") == code


def test_unknown_direction_is_rejected():
    with pytest.raises(SeedError, match="코드로 바꿀 수 없음"):
        direction_code("약간 큼", "TS-115-GIS 99")


def test_table_name_of():
    assert table_name_of("파일1 TS-115-GIS (115 kV GIS)") == "TS-115-GIS"
    assert table_name_of("파일1 TS-SG (22 kV 수배전반) III 차단기") == "TS-SG"


def test_product_row_defaults_and_design_card():
    """Scenario: 설계 사례 카드."""
    row = product_row({"product_code": "X", "description": "[설계 사례 카드, 판정 기준 아님]"})
    assert row["lifecycle_status"] == "UNKNOWN"
    assert row["is_assumed"] == "N"
    assert row["is_design_card"] is True
