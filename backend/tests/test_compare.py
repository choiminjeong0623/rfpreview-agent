"""판정 규칙·숫자 검사·손실 계산 단위 테스트 (DB 없이). 명세 compliance-judgment, bid-outputs,
loss-evaluation, proposal-points의 Scenario를 코드 수준에서 확인한다."""

from rfp_agent.pipeline.compare import ReqValue, compare, precheck, unit_key
from rfp_agent.pipeline.loss import DOLLAR_PER_KW, compute, price_kind
from rfp_agent.pipeline.numbers import fill, fmt, josa
from rfp_agent.pipeline.products import ProductValue


def req(num, unit, item_key="rated_current", operator=None, time_s=None, cell_form="NUMBER",
        raw=None, multi=False):
    return ReqValue(raw=raw or f"{num}", cell_form=cell_form, num=num, operator=operator,
                    unit=unit, time_s=time_s, item_key=item_key, basis_standard=None, flag=None,
                    multi=multi)


def test_requirement_above_product_is_deviation():
    """Scenario: 요구를 넘는 제품 — 4,000 A 요구, 제품 3,150 A는 일탈 후보."""
    v = compare(req(4000, "A"), ProductValue("3150", 3150, "A"), "GE", "HIGHER")
    assert (v.result, v.reason, v.margin) == ("DEVIATION_CANDIDATE", "NOT_MET", None)


def test_missing_product_value_and_unit_difference():
    """Scenario: 제품값 없음 / 단위가 다름 — 확인 필요, 여유 계산 안 함."""
    gas = compare(req(0.5, "%", "gas_leakage_rate", "<"), None, "LT", "LOWER")
    assert (gas.result, gas.reason, gas.margin_direction) == (
        "NEEDS_REVIEW", "NO_PRODUCT_VALUE", "NOT_CALC")
    unit = compare(req(3.15, "kA"), ProductValue("3150", 3150, "A"), "GE", "HIGHER")
    assert (unit.result, unit.reason, unit.margin) == ("NEEDS_REVIEW", "UNIT_DIFF", None)
    assert unit_key("kVrms") == unit_key("kV") and unit_key("℃") == unit_key("°C")


def test_time_ratio_margin():
    """Scenario: 40 kA 1초 요구, 3초 제품 — 준수, 시간 3배, 강점."""
    v = compare(req(40, "kA", "short_time_current", time_s=1),
                ProductValue("40 kA (3초)", 40, "kA", time_s=3), "GE", "HIGHER")
    assert (v.result, v.margin, v.margin_kind, v.margin_direction) == (
        "COMPLY", 3, "TIME_RATIO", "STRENGTH")
    shorter = compare(req(40, "kA", "short_time_current", time_s=3),
                      ProductValue("40 kA (1초)", 40, "kA", time_s=1), "GE", "HIGHER")
    assert (shorter.result, shorter.reason) == ("NEEDS_REVIEW", "CONDITION_DIFF")


def test_margin_without_strength():
    """Scenario: 강점이 아닌 여유 — 무게처럼 강점 방향이 "강점 아님"이면 여유 방향은 강점 아님."""
    v = compare(req(2000, "kg", "weight", "<="), ProductValue("318", 318, "kg"), "LE", "NONE")
    assert (v.result, v.margin, v.margin_direction) == ("COMPLY", 1682, "NOT_STRENGTH")
    voltage = compare(req(125, "kV", "rated_voltage_um"), ProductValue("145", 145, "kV"), "GE",
                      "NONE")
    assert (voltage.result, voltage.margin_direction) == ("COMPLY", "NOT_STRENGTH")


def test_boundary_and_multi_value():
    """요구 "<0.5"와 제품 "≤0.5"는 경계값(확인 필요), 한 칸의 값 여럿은 질의 후보."""
    v = compare(req(0.5, "%", "gas_leakage_rate", "<"),
                ProductValue("0.5 % 이하", 0.5, "%", "<="), "LT", "LOWER")
    assert (v.result, v.reason) == ("NEEDS_REVIEW", "BOUNDARY")
    multi = precheck(req(2000, "A", multi=True), "GE")
    assert (multi.result, multi.reason) == ("QUERY_CANDIDATE", "MULTI_VALUE")


def test_number_mismatch():
    """Scenario: 근거와 다른 숫자 — 채운 문장 속 숫자가 근거와 다르면 불일치."""
    ok = fill("요구 {v1} A, 제품 {v2} A", {"v1": fmt(4000), "v2": "3150"})
    assert (ok.text, ok.check) == ("요구 4,000 A, 제품 3150 A", "OK")
    bad = fill("요구 {v1} A, 제품 3,000 A", {"v1": fmt(4000)})
    assert bad.check == "MISMATCH" and "3000" in bad.detail
    leftover = fill("요구 {v9}", {"v1": "1"})
    assert leftover.check == "MISMATCH"


def test_loss_evaluation_case_5():
    """Scenario: 사례 5 — 4,500/3,200/1,300 $/kW × 60/300/8 kW = 1,240,400 $."""
    total, formula = compute({"noload": 4500, "load": 3200, "aux": 1300},
                             {"noload": 60, "load": 300, "aux": 8})
    assert total == 1_240_400
    assert formula.endswith("= 270,000 + 960,000 + 10,400 = 1,240,400 $")


def test_loss_without_values():
    """Scenario: 손실값 없음 — 합계는 비어 있다."""
    total, formula = compute({"noload": 4500, "load": 3200, "aux": 1300},
                             {"noload": None, "load": 300, "aux": 8})
    assert total is None and "손실값 없음" in formula
    assert DOLLAR_PER_KW.match("US$/kW") and not DOLLAR_PER_KW.match("KRW/kW")
    assert [price_kind(n) for n in ("No-load loss", "Load loss", "Auxiliary loss")] == [
        "noload", "load", "aux"]


def test_paired_particles_follow_filled_value():
    """채운 값 뒤의 "과(와)", "(으)로" 같은 조사를 앞 글자 받침에 맞게 고른다."""
    filled = fill("가스 누설률이 {v1}과(와) {v2}(으)로 다릅니다.", {"v1": "1 % 이내", "v2": "<0.5"})
    assert filled.text == "가스 누설률이 1 % 이내와 <0.5로 다릅니다." and filled.check == "OK"
    assert josa("3150 A과(와) 정격 전류을(를)") == "3150 A와 정격 전류를"
    assert josa("40 kA 1(으)로, 파일(으)로, 품목(으)로") == "40 kA 1로, 파일로, 품목으로"


def test_josa_after_placeholder():
    """Scenario: 제품 코드 뒤 조사 — 자리표시자 뒤 한쪽 조사를 채운 값에 맞춰 고른다."""
    assert fill("{p}는 {v2}로", {"p": "GIS-145-40", "v2": "650"}).text == "GIS-145-40은 650으로"
    assert fill("{p}는 {v2}를 견뎌", {"p": "TRF-HV", "v2": "40 kA 3 s"}).text \
        == "TRF-HV는 40 kA 3 s를 견뎌"
    assert fill("{p}의 값은 {v2}로.", {"p": "GIS-245-50", "v2": "3,150 A"}).text \
        == "GIS-245-50의 값은 3,150 A로."
    assert fill("{p}가격", {"p": "GIS-145-40"}).text == "GIS-145-40가격"     # 낱말 일부는 그대로
