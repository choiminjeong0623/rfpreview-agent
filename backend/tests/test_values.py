"""FR-05 값 정리 (명세 value-normalization, evidence-integrity 가림 표시)."""

import pytest

from rfp_agent.pipeline.values import cell_values, evaluate_formula, sentence_values


def test_symbol_number_keeps_raw_text():
    """Scenario: 기호가 붙은 숫자."""
    [v] = cell_values("<0.5", "%")
    assert (v.cell_form, v.num_value, v.operator, v.unit_raw, v.raw_text) == (
        "NUMBER", 0.5, "<", "%", "<0.5")


def test_delegated_standard():
    """Scenario: 규격 위임."""
    [v] = cell_values("As per IEC:62271-100", None)
    assert v.cell_form == "DELEGATED"
    assert v.delegated_std == "IEC 62271-100"
    assert v.num_value is None


def test_formula_is_computed_by_code():
    """Scenario: 1.1 × 125/√3."""
    [v] = cell_values("1.1 x 125/√3", "kV")
    assert v.cell_form == "FORMULA"
    assert v.num_value == pytest.approx(79.39, abs=0.01)
    assert v.unit_raw == "kV"


def test_formula_outside_allowed_operators_needs_review():
    assert evaluate_formula("2 ** 10") is None
    [v] = cell_values("2 × 10^2", "kV")
    assert v.cell_form == "FORMULA" and v.num_value is None
    assert v.flag == "FORMULA_NOT_ALLOWED"


def test_units_are_not_converted():
    values = sentence_values("Maximum ambient temperature 104 deg F (40 deg C)")
    assert [(v.num_value, v.unit_raw) for v in values] == [(104, "deg F"), (40, "deg C")]
    assert values[0].cond_raw is None       # 괄호 안이 값이면 조건이 아니다


def test_redacted_value_is_empty_not_guessed():
    """Scenario: 가림 표시."""
    [v] = cell_values("[REDACTED]", "kV")
    assert v.cell_form == "EMPTY" and v.flag == "REDACTED" and v.num_value is None


def test_missing_unit_is_flagged():
    [v] = cell_values("40", None)
    assert v.flag == "UNIT_MISSING"


def test_multi_value_cell():
    values = cell_values("3000/2500", "A")
    assert [(v.num_value, v.seq) for v in values] == [(3000, 1), (2500, 2)]


def test_korean_bounds_and_ranges():
    [v] = sentence_values("가스 누기량은 연간 0.5 % 이내로 되어야 한다.")
    assert (v.num_value, v.operator) == (0.5, "<=")
    [v] = sentence_values("between the limits of 47 Hz and 51 Hz")[-1:]
    assert v.flag == "RANGE" and v.operator == "<="


def test_site_numbers_are_not_values():
    values = sentence_values("UPS : 5kVA (수상전기실) 10kVA (154kV 변전소)")
    assert [v.num_value for v in values] == [5, 10]


def test_standard_titles_have_no_values():
    assert sentence_values("Part 103: Switches for rated voltages above 1 kV up to 52 kV") == []


def test_auxiliary_circuit_voltage_is_not_highest_voltage(seeded_db):
    """보조 회로 정격 전압은 "Rated voltage"로 시작해도 설비 최고 전압에 연결하지 않는다."""
    from rfp_agent.pipeline import dictionaries
    from rfp_agent.pipeline.values import item_key_of

    dicts = dictionaries.load(seeded_db).values
    assert item_key_of("Rated voltage of auxiliary circuits", dicts) == "aux_circuit_voltage"
    assert item_key_of("Rated supply voltage of auxiliary and control circuits",
                       dicts) == "aux_circuit_voltage"
    assert item_key_of("보조 회로 정격 전압", dicts) == "aux_circuit_voltage"
    # 원래 설비 최고 전압 표현은 그대로
    assert item_key_of("Rated voltage", dicts) == "rated_voltage_um"
    assert item_key_of("Rated voltage (Ur)", dicts) == "rated_voltage_um"
