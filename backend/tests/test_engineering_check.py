"""FR-12 공학 규칙 검산. 명세 engineering-check와 bid-outputs(검산 질의)의 Scenario.

합성 묶음 A 데이터시트로 확인한다. 실제 문서(파일 1 TS-230-GIS)로 하는 확인은 test_corpus.py에 있다.
"""

import pytest
from docx import Document

from rfp_agent.pipeline import queries
from rfp_agent.pipeline.engineering import matches, r10
from rfp_agent.pipeline.run import RunContext, create_run, execute_run
from tests.docx_factory import _datasheet

VERSION = "test-dict-v1"
BREAKER_230 = [
    ["I", "245 kV Circuit Breaker", "", "", ""],
    ["1", "Rated frequency", "Hz", "50", ""],
    ["2", "Rated short-circuit breaking current", "kA", "50", ""],
    ["3", "Rated short-circuit making current", "kA", "125", ""],
    ["4", "Rated peak withstand current", "kA", "100", ""],
    ["II", "245 kV Disconnecting Switches", "", "", ""],
    ["5", "Rated short-time withstand current (3 sec)", "kA", "40", ""],
    ["6", "Rated peak withstand current", "kA", "100", ""],
]


def build_check_spec(path, rows_230=BREAKER_230):
    doc = Document()
    doc.add_paragraph("SCHEDULE OF TECHNICAL DATA")
    doc.add_paragraph("1. DATA SHEET")
    _datasheet(doc, "TS-230-CB", rows_230)
    _datasheet(doc, "TS-115-GIS", [
        ["1", "Rated frequency", "Hz", "50", ""],
        ["2", "Rated short-time withstand current, (1 sec.)", "kA", "40", ""],
        ["3", "Rated peak withstand current", "kA", "100", ""],
    ])
    _datasheet(doc, "TS-SG", [
        ["1", "Rated frequency", "Hz", "50", ""],
        ["2", "Short circuit breaking current", "kA", "25", ""],
        ["3", "Rated peak withstand current", "kA", "63", ""],
    ])
    _datasheet(doc, "TS-145-DS", [
        ["1", "Rated short-time withstand current, (1 sec.)", "kA", "31.5", ""],
        ["2", "Rated peak withstand current", "kA", "80", ""],
    ])
    _datasheet(doc, "TS-60-SW", [
        ["1", "Rated frequency", "Hz", "60", ""],
        ["2", "Rated short-time withstand current, (1 sec.)", "kA", "40", ""],
        ["3", "Rated peak withstand current", "kA", "104", ""],
    ])
    doc.save(str(path))
    return path


def run_once(conn, paths):
    run_id = create_run(conn, VERSION, None)
    assert execute_run(RunContext(conn, VERSION, None, None), run_id, paths) == "ENGINEER_REVIEW"
    return run_id


def check_in(conn, run_id, table, peak, ik=None):
    rows = [c for c in queries.run_checks(conn, run_id)
            if c["locations"][0]["table_name"] == table and float(c["peak_ka"]) == peak
            and (ik is None or float(c["ik_ka"]) == ik)]
    assert len(rows) == 1, (table, peak, rows)
    return rows[0]


@pytest.fixture
def checked(db, tmp_path):
    run_id = run_once(db, [build_check_spec(tmp_path / "synthetic_judgment_check.docx")])
    return db, run_id


def test_115kv_gis_passes(checked):
    """Scenario: 115 kV GIS — 40 kA, 100 kA, 50 Hz이면 통과."""
    conn, run_id = checked
    c = check_in(conn, run_id, "TS-115-GIS", 100)
    assert (c["result"], float(c["expected_ka"]), float(c["factor"])) == ("PASS", 100, 2.5)


def test_230kv_breaker_violation_is_query(checked):
    """Scenario: 검산 위반 질의 ·
    Scenario: 230 kV 차단기 — 차단 50 kA, 최대 순간 100 kA, 50 Hz이면 위반(계산값 125)이고
    질의 후보가 된다."""
    conn, run_id = checked
    c = check_in(conn, run_id, "TS-230-CB", 100, ik=50)
    assert (c["result"], float(c["expected_ka"])) == ("VIOLATION", 125)
    [query] = [i for i in queries.run_outputs(conn, run_id, "QUERY")
               if any(s["check_id"] == c["check_id"] for s in i["sources"])]
    assert "100 kA" in query["text_draft"] and "125 kA" in query["text_draft"]
    assert query["number_check"] == "OK" and query["status"] == "DRAFT"
    assert len(query["locations"]) == 2          # 최대 순간 전류 행 + 차단 전류 행


def test_making_current_in_same_part(checked):
    """Scenario: 투입 전류 — 같은 부위의 차단 전류 50 kA × 2.5 = 125 kA이면 통과."""
    conn, run_id = checked
    making = [c for c in queries.run_checks(conn, run_id)
              if c["peak_item_key"] == "making_current"]
    assert [(c["result"], float(c["peak_ka"])) for c in making] == [("PASS", 125)]


def test_only_same_part(checked):
    """Scenario: 다른 부위 값 — 단로기(II) 100 kA는 같은 부위의 40 kA와만 맞춰 보고 통과."""
    conn, run_id = checked
    rows = [c for c in queries.run_checks(conn, run_id)
            if c["locations"][0]["table_name"] == "TS-230-CB" and float(c["peak_ka"]) == 100]
    assert sorted((float(c["ik_ka"]), c["result"]) for c in rows) == [
        (40, "PASS"), (50, "VIOLATION")]


def test_standard_value_rounding(checked):
    """Scenario: 표준값 ·
    Scenario: 규격 표준값 — 25 kA × 2.5 = 62.5는 표준값 63 kA와 같다고 보고 통과."""
    conn, run_id = checked
    assert check_in(conn, run_id, "TS-SG", 63)["result"] == "PASS"


def test_60hz_factor(checked):
    """Scenario: 60 Hz — 40 kA × 2.6 = 104 kA이면 통과."""
    conn, run_id = checked
    c = check_in(conn, run_id, "TS-60-SW", 104)
    assert (c["result"], float(c["factor"])) == ("PASS", 2.6)


def test_no_frequency_needs_review(checked):
    """Scenario: 주파수 없음 — 같은 표에서 주파수를 못 찾으면 확인 필요, 질의는 만들지 않는다."""
    conn, run_id = checked
    c = check_in(conn, run_id, "TS-145-DS", 80)
    assert (c["result"], c["reason_code"], c["expected_ka"]) == (
        "NEEDS_REVIEW", "NO_FREQUENCY", None)
    queries_from_checks = [i for i in queries.run_outputs(conn, run_id, "QUERY")
                           if any(s["check_id"] for s in i["sources"])]
    assert len(queries_from_checks) == 1         # 230 kV 위반 한 건뿐


def test_same_query_in_two_documents(db, tmp_path):
    """Scenario: 두 문서에 같은 질의 — 230 kV 차단기 100 kA 질의가 두 문서에 있으면 1건."""
    paths = [build_check_spec(tmp_path / "synthetic_judgment_check.docx"),
             build_check_spec(tmp_path / "synthetic_feeder_check.docx")]
    run_id = run_once(db, paths)
    [query] = [i for i in queries.run_outputs(db, run_id, "QUERY")
               if any(s["check_id"] for s in i["sources"])]
    assert {loc["file_no"] for loc in query["locations"]} == {91, 92}


@pytest.mark.parametrize(("value", "expected"), [(62.5, 63), (78.75, 80), (100, 100), (104, 100),
                                                 (125, 125), (157.5, 160)])
def test_r10(value, expected):
    assert r10(value) == pytest.approx(expected)


def test_matches_exact_or_standard_value():
    """50 Hz는 규격 표준값까지, 60 Hz는 정수로 올린 값까지 같다고 본다."""
    assert matches(104, 104, 2.6) and matches(82, 81.9, 2.6) and not matches(100, 104, 2.6)
    assert matches(63, 62.5, 2.5) and matches(80, 78.75, 2.5) and not matches(100, 125, 2.5)
