"""FR-12 공학 규칙 검산. 규칙 하나만 쓴다 [결정]:
최대 순간 전류 = 단시간 전류 × 2.5(50 Hz) / × 2.6(60 Hz).

같은 표·같은 부위(설비 묶음)의 값끼리만 맞춰 본다. 계산·판정은 코드만 하고 (CR-01), 단위는 바꾸지
않는다 (CR-10). 위반이면 FR-09 질의 후보가 된다.
"""

import math
from collections import defaultdict
from dataclasses import dataclass

import psycopg

from rfp_agent.pipeline.compare import unit_key
from rfp_agent.pipeline.judge import build_groups, load_values

RULE_CODE = "B1"
FACTORS = {"50": 2.5, "60": 2.6}
IK_KEYS = ("short_time_current", "breaking_current")     # 단시간 전류가 없으면 차단 전류
PEAK_KEYS = ("peak_current", "making_current")
R10 = (1.0, 1.25, 1.6, 2.0, 2.5, 3.15, 4.0, 5.0, 6.3, 8.0, 10.0)
TOLERANCE = 0.01


@dataclass
class Check:
    ik: dict
    peak: dict
    freq: dict | None
    factor: float | None
    expected: float | None
    result: str                 # PASS / VIOLATION / NEEDS_REVIEW
    reason: str | None = None   # NO_FREQUENCY, MULTI_FREQUENCY, MULTI_IK, UNIT_DIFF


def r10(value: float) -> float:
    """규격 표준값(R10 수열)으로 맞춘 값. 25 kA × 2.5 = 62.5 → 63, 31.5 × 2.5 = 78.75 → 80."""
    decade = 10 ** math.floor(math.log10(value))
    return min((s * decade for s in R10), key=lambda x: abs(x - value))


def matches(peak: float, expected: float, factor: float) -> bool:
    """계산값 그대로, 정수로 올린 값(60 Hz 31.5 kA × 2.6 = 81.9 → 82), 50 Hz면 규격 표준값까지
    같다고 본다.

    60 Hz에 50 Hz 표준값(40 kA → 100 kA)을 옮겨 적은 것은 위반으로 남긴다. [제안]
    """
    allowed = [expected, math.floor(expected + 0.5)]
    if factor == FACTORS["50"]:
        allowed.append(r10(expected))
    return any(abs(peak - a) < TOLERANCE for a in allowed)


def allowed_values(expected: float, factor: float) -> list[float]:
    """같다고 보는 최대 순간 전류: 계산값, 정수 반올림, 50 Hz면 규격 표준값(R10)."""
    out = [expected, math.floor(expected + 0.5)]
    if factor == FACTORS["50"]:
        out.append(r10(expected))
    return sorted(set(out))


def peak_check(ik_ka: float, frequency_hz: float, peak_ka: float) -> dict:
    """검산 확인 (add-check-calculator): 사람이 넣은 값으로 분석 검산과 같은 규칙을 적용한다.

    저장하지 않고 판정을 바꾸지 않는다. 주파수가 50·60이 아니면 확인 필요.
    """
    factor = FACTORS.get(f"{float(frequency_hz):g}")
    if factor is None:
        return {"rule_code": RULE_CODE, "factor": None, "expected_ka": None, "allowed_ka": [],
                "result": "NEEDS_REVIEW", "reason_code": "NO_FACTOR"}
    expected = round(ik_ka * factor, 2)
    ok = matches(peak_ka, expected, factor)
    return {"rule_code": RULE_CODE, "factor": factor, "expected_ka": expected,
            "allowed_ka": allowed_values(expected, factor),
            "result": "PASS" if ok else "VIOLATION", "reason_code": None}


def _numeric(values: list[dict], keys: tuple[str, ...]) -> list[dict]:
    return [v for v in values if v["item_key"] in keys and v["num_value"] is not None
            and v["flag"] != "RANGE"]


def _frequency(group: list[dict], table: list[dict]) -> tuple[list[dict], set[str]]:
    """같은 부위의 주파수, 없으면 같은 표의 주파수."""
    for pool in (group, table):
        found = [v for v in _numeric(pool, ("rated_frequency",))
                 if unit_key(v["unit_raw"]) == "hz"]
        if found:
            return found, {f"{float(v['num_value']):g}" for v in found}
    return [], set()


def check_group(group: list[dict], table: list[dict]) -> list[Check]:
    peaks = [v for v in _numeric(group, PEAK_KEYS) if v["represents"]]
    iks = _numeric(group, IK_KEYS)
    if not peaks or not iks:
        return []
    # 단시간 전류가 있으면 그것, 없으면 차단 전류 (명세서 예: 230 kV 차단기 차단 50 kA)
    base = [v for v in iks if v["item_key"] == "short_time_current"] or iks
    ik = base[0]
    ik_nums = {float(v["num_value"]) for v in base if unit_key(v["unit_raw"]) == "ka"}
    freqs, freq_texts = _frequency(group, table)
    checks = []
    for peak in peaks:
        freq = freqs[0] if freqs else None
        if unit_key(peak["unit_raw"]) != "ka" or unit_key(ik["unit_raw"]) != "ka":
            checks.append(Check(ik, peak, freq, None, None, "NEEDS_REVIEW", "UNIT_DIFF"))
        elif len(ik_nums) != 1:
            checks.append(Check(ik, peak, freq, None, None, "NEEDS_REVIEW", "MULTI_IK"))
        elif not freq_texts:
            checks.append(Check(ik, peak, None, None, None, "NEEDS_REVIEW", "NO_FREQUENCY"))
        elif len(freq_texts) > 1 or next(iter(freq_texts)) not in FACTORS:
            checks.append(Check(ik, peak, freq, None, None, "NEEDS_REVIEW", "MULTI_FREQUENCY"))
        else:
            factor = FACTORS[next(iter(freq_texts))]
            expected = round(next(iter(ik_nums)) * factor, 2)
            ok = matches(float(peak["num_value"]), expected, factor)
            checks.append(Check(ik, peak, freq, factor, expected, "PASS" if ok else "VIOLATION"))
    return checks


def _table_key(v: dict) -> tuple:
    """쪽 넘김으로 나뉜 같은 이름 표(파일 1 TS-230-DS)는 한 표로 본다."""
    return (v["document_id"], v["table_name"] or v["table_id"])


def find_checks(conn: psycopg.Connection, document_ids: list[int]) -> list[Check]:
    values = load_values(conn, document_ids)
    build_groups(conn, values)                  # 값마다 설비 묶음(v["group"])을 붙인다
    by_group: dict[str, list[dict]] = defaultdict(list)
    by_table: dict[tuple, list[dict]] = defaultdict(list)
    for v in values:
        if v["table_id"]:                       # 문장 값은 같은 부위인지 알 수 없어 보지 않는다
            by_group[v["group"]].append(v)
            by_table[_table_key(v)].append(v)
    checks = []
    for key in sorted(by_group, key=lambda k: by_group[k][0]["value_id"]):
        group = by_group[key]
        checks += check_group(group, by_table[_table_key(group[0])])
    return checks


def clear_checks(conn: psycopg.Connection, run_id: int) -> None:
    # 목록 항목의 출처가 검산을 가리키므로 먼저 지운다 (목록 단계에서 다시 만든다)
    conn.execute("DELETE FROM output_item_source WHERE check_id IN "
                 "(SELECT check_id FROM engineering_check WHERE run_id = %s)", (run_id,))
    conn.execute("DELETE FROM engineering_check WHERE run_id = %s", (run_id,))


def build_checks(conn: psycopg.Connection, run_id: int, document_ids: list[int]) -> int:
    checks = find_checks(conn, document_ids)
    with conn.transaction():
        clear_checks(conn, run_id)
        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO engineering_check (run_id, rule_code, ik_value_id, peak_value_id,
                       freq_value_id, expected_ka, result, factor, reason_code)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                [(run_id, RULE_CODE, c.ik["value_id"], c.peak["value_id"],
                  c.freq["value_id"] if c.freq else None, c.expected, c.result, c.factor,
                  c.reason) for c in checks])
    return len(checks)
