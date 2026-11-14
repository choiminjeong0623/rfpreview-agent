"""실제 RFP 문서로 명세 Scenario를 확인한다.

원문은 고객 자료라 저장소에 없다 (data/private). 원문·txt·테스트 DB가 모두 있을 때만 돈다.
줄 번호는 팀 추출 txt 기준이다.
"""

import os

import psycopg
import pytest

from rfp_agent.config import get_settings
from rfp_agent.db.migrate import migrate
from rfp_agent.db.seed import dict_version, seed_products, seed_rules
from rfp_agent.pipeline import dictionaries, ocr, queries
from rfp_agent.pipeline.document import process_document
from rfp_agent.pipeline.run import RunContext, create_run, execute_run
from tests.conftest import JUDGMENT_LOSS_FILE, JUDGMENT_PRODUCT_FILES, FakeLLM

SETTINGS = get_settings()
FILES = {
    1: "RFP01 Bidding Forms", 2: "RFP02 Employers Requirement", 3: "RFP03 115kV GIS Requisition",
    4: "RFP04 GIS Specification", 6: "RFP06 154kV GIS Specification",
    8: "RFP08 Circuit Breaker Specification", 13: "RFP13 Medium-Voltage Switchgear",
    18: "RFP18 Electric",
    19: "RFP19 설계기준", 22: "RFP22 154kV",
}

pytestmark = pytest.mark.skipif(
    not (SETTINGS.docx_dir.exists() and SETTINGS.txt_dir.exists()
         and os.environ.get("TEST_DATABASE_URL")),
    reason="RFP 원문(data/private)이나 TEST_DATABASE_URL이 없어 실제 문서 테스트를 건너뜀",
)


def path_of(file_no: int):
    return next(p for p in SETTINGS.docx_dir.glob("*.docx") if FILES[file_no] in p.name)


@pytest.fixture(scope="module")
def conn():
    with psycopg.connect(os.environ["TEST_DATABASE_URL"]) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
        conn.commit()
        migrate(conn, SETTINGS.migrations_dir)
        seed_rules(conn, SETTINGS.seed_dir)
        seed_products(conn, JUDGMENT_PRODUCT_FILES, JUDGMENT_LOSS_FILE)
        conn.commit()
        yield conn


def run(conn, file_nos, llm=None):
    version = dict_version(SETTINGS.seed_dir)
    run_id = create_run(conn, version, llm)
    stage = execute_run(RunContext(conn, version, llm, SETTINGS.txt_dir), run_id,
                        [path_of(n) for n in file_nos])
    assert stage == "ENGINEER_REVIEW"
    return run_id


@pytest.fixture(scope="module")
def main_run(conn):
    return run(conn, [1, 3, 6, 8, 13, 18])


def requirement_at(conn, run_id, file_no, line):
    row = conn.execute(
        """SELECT q.requirement_id FROM requirement q
           JOIN run_document rd ON rd.document_id = q.document_id AND rd.run_id = %s
           JOIN document d ON d.document_id = q.document_id AND d.file_no = %s
           JOIN requirement_location rl ON rl.requirement_id = q.requirement_id
           JOIN source_location l ON l.location_id = rl.location_id
           WHERE l.line_start <= %s AND COALESCE(l.line_end, l.line_start) >= %s
           ORDER BY l.line_start DESC LIMIT 1""", (run_id, file_no, line, line)).fetchone()
    assert row, f"파일 {file_no} {line}행 요구사항 없음"
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        req = cur.execute("SELECT * FROM requirement WHERE requirement_id = %s",
                          (row[0],)).fetchone()
    return queries._attach(conn, [req])[0]


def document(conn, run_id, file_no):
    return next(d for d in queries.run_documents(conn, run_id) if d["file_no"] == file_no)


# ---------------------------------------------------------------- FR-01

def test_bid_form_classification(conn, main_run):
    """Scenario: 입찰 서식."""
    d = document(conn, main_run, 1)
    assert (d["bundle"], d["doc_kind"], d["judge_target"], d["standard_system"]) == (
        "A", "BID_FORM", True, "IEC")
    assert d["line_basis"] == "TXT"


def test_us_spec_is_not_judged(conn, main_run):
    """Scenario: 판정 대상이 아닌 미국 사양서."""
    d = document(conn, main_run, 13)
    assert (d["bundle"], d["doc_kind"], d["judge_target"], d["standard_system"]) == (
        "C", "REQUIREMENT_SPEC", False, "IEEE_UL")


def test_image_only_document(conn, monkeypatch):
    """Scenario: 이미지만 있는 문서 — OCR 엔진 없이는 판독 불가."""
    monkeypatch.setattr(ocr, "available", lambda: False)
    result = process_document(conn, path_of(8), dictionaries.load(conn), "corpus-ocr-off", None,
                              None)
    conn.commit()
    assert (result.readable, result.requirement_count) == (False, 0)


@pytest.mark.skipif(ocr.engine_version() is None, reason="Tesseract 없음")
def test_image_document_with_ocr(conn, main_run):
    """Scenario: OCR로 읽은 이미지 문서 — 판독 가능, OCR 요구사항, 확인 필요 (add-ocr)."""
    d = document(conn, main_run, 8)
    assert d["readable"] and d["requirements"] > 0 and d["needs_review"] and d["ocr_lines"] > 0
    kinds = {r[0] for r in conn.execute(
        "SELECT DISTINCT extracted_by FROM requirement WHERE document_id = %s",
        (d["document_id"],))}
    assert kinds == {"OCR"}


# ---------------------------------------------------------------- FR-02

def test_toc_and_body(conn, main_run):
    """Scenario: 목차와 본문."""
    doc_id = document(conn, main_run, 3)["document_id"]
    rows = conn.execute("SELECT line_start, is_toc FROM section WHERE document_id = %s AND "
                        "title LIKE 'CLARIFICATION, EXCEPTION%%' ORDER BY line_start",
                        (doc_id,)).fetchall()
    assert rows == [(18, True), (188, False)]


def test_split_gis_table(conn, main_run):
    """Scenario: 4개로 나뉜 115 kV GIS 표 / 20번 아래 3줄."""
    doc_id = document(conn, main_run, 1)["document_id"]
    [(table_id, nos)] = conn.execute(
        "SELECT table_id, source_table_nos FROM doc_table WHERE document_id = %s "
        "AND table_name = 'TS-115-GIS'", (doc_id,)).fetchall()
    assert len(nos) >= 4                    # 쪽 넘김으로 나뉜 Word 표 여러 개 (원문 docx는 8개)
    items = [r[0] for r in conn.execute(
        "SELECT item_no FROM table_row WHERE table_id = %s ORDER BY row_order", (table_id,))]
    # 로마 숫자 구분 행(I, II, …)마다 번호가 다시 시작한다. 첫 구분(I)은 1~27이 끊김 없이 이어진다.
    part_one = items[items.index("I") + 1:items.index("II")]
    assert [int(i) for i in part_one if i.isdigit()] == list(range(1, 28))
    children = conn.execute(
        "SELECT c.item_no FROM table_row c JOIN table_row p ON p.row_id = c.parent_row_id "
        "WHERE c.table_id = %s AND p.item_no = '20' ORDER BY c.row_order", (table_id,)).fetchall()
    assert [c[0] for c in children] == ["20-1", "20-2", "20-3"]
    assert not any(i and i.strip().lower().startswith("no") for i in items)


# ---------------------------------------------------------------- FR-03·04·05

def test_datasheet_row_7459(conn, main_run):
    """Scenario: 데이터시트 행 / 시간 조건."""
    req = requirement_at(conn, main_run, 1, 7459)
    assert req["source_kind"] == "TABLE_CELL"
    [loc] = [x for x in req["locations"] if x["file_no"] == 1]
    assert (loc["table_name"], loc["item_no"]) == ("TS-115-GIS", "16")
    [v] = req["values"]
    assert (float(v["num_value"]), v["unit_raw"], float(v["cond_time_s"]), v["item_key"]) == (
        40, "kA", 1, "short_time_current")


def test_writing_rule_7419(conn, main_run):
    """Scenario: 작성 규칙."""
    assert requirement_at(conn, main_run, 1, 7419)["req_kind"] == "WRITING_RULE"


def test_loss_clause_types_8238(conn, main_run):
    """Scenario: 손실 환산 조항."""
    types = requirement_at(conn, main_run, 1, 8238)["types"]
    assert [(t["type_code"], t["is_primary"]) for t in types][:2] == [
        ("COST", True), ("TECH_PERF", False)]


def test_supplier_marks_are_separate(conn, main_run):
    """Scenario: 공급사 표시."""
    req = requirement_at(conn, main_run, 18, 208)
    assert req["supplier_mark"] == "C"
    assert req["source_kind"] == "SUPPLIER_ANSWER"


def test_fahrenheit_and_celsius_kept(conn, main_run):
    """Scenario: 화씨와 섭씨."""
    values = requirement_at(conn, main_run, 13, 113)["values"]
    units = [(float(v["num_value"]), v["unit_raw"]) for v in values]
    assert (104, "deg F") in units and (40, "deg C") in units


# ---------------------------------------------------------------- FR-06

def risks(conn, run_id, kind):
    return [r for r in queries.run_risks(conn, run_id) if r["risk_kind"] == kind]


def member_lines(risk):
    return sorted((loc["file_no"], loc["line_start"]) for m in risk["members"]
                  for loc in m["locations"])


def test_deemed_to_be_accepted(conn, main_run):
    hits = [r for r in risks(conn, main_run, "BLANKET") if (3, 190) in member_lines(r)]
    assert len(hits) == 1 and hits[0]["expression"] == "deemed"


def test_gas_leakage_mismatch(conn, main_run):
    """Scenario: 적용 대상이 다른 가스 누설."""
    [hit] = [r for r in risks(conn, main_run, "VALUE_MISMATCH")
             if r["item_key"] == "gas_leakage_rate"]
    assert member_lines(hit) == [(6, 174), (6, 278)]
    assert "적용 대상과 근거 규격이 다름" in hit["facts"]


def test_ambient_temperature_is_not_a_candidate(conn, main_run):
    """Scenario: 적용 대상이 다른 주위 온도."""
    assert not [r for r in risks(conn, main_run, "VALUE_MISMATCH")
                if r["item_key"] == "ambient_temp_max" and member_lines(r)[0][0] == 1]


def test_ups_capacity_across_documents(conn):
    """Scenario: 문서를 넘는 UPS 용량."""
    run_id = run(conn, [19, 22])
    hits = [r for r in risks(conn, run_id, "VALUE_MISMATCH") if r["item_key"] == "rated_capacity"]
    assert [member_lines(r) for r in hits] == [[(19, 301), (22, 3008)]]


def test_pair_candidate_and_section_sized_ai_inputs(conn):
    """Scenario: 데이터시트가 겹치는 두 문서."""
    llm = FakeLLM()
    run_id = run(conn, [1, 2], llm=llm)
    [pair] = queries.run_pairs(conn, run_id)
    assert (pair["file_no_a"], pair["file_no_b"], pair["status"]) == (1, 2, "CANDIDATE")
    assert "데이터시트 항목" in pair["evidence"]
    label_prompts = [p for p in llm.prompts if "절 제목:" in p]
    assert label_prompts and all(p.count("절 제목:") == 1 for p in label_prompts)
    assert max(len(p) for p in llm.prompts) < 40_000


# ---------------------------------------------------------------- FR-07·08·09·13·14

def judgments_at(conn, run_id, file_no, line):
    return [j for j in _current_judgments(conn, run_id)
            if (file_no, line) in {(loc["file_no"], loc["line_start"]) for loc in j["locations"]}]


def _all(query, conn, run_id):
    rows, offset = [], 0
    while batch := query(conn, run_id, limit=500, offset=offset):
        rows += batch
        offset += 500
    return rows


def _current_judgments(conn, run_id):
    return _all(queries.run_judgments, conn, run_id)


def test_main_bus_4000a_deviation(conn, main_run):
    """Scenario: 요구를 넘는 제품 / 세 곳에 반복된 일탈.

    견적표 1784행은 아직 추출되지 않는다 [확인 필요]."""
    [j] = judgments_at(conn, main_run, 1, 7100)
    assert (j["product_code"], j["result"]) == ("GIS-245-50", "DEVIATION_CANDIDATE")
    [item] = [i for i in queries.run_outputs(conn, main_run, "DEVIATION")
              if (1, 7100) in {(loc["file_no"], loc["line_start"]) for loc in i["locations"]}]
    lines = {(loc["file_no"], loc["line_start"]) for loc in item["locations"]}
    assert {(1, 7100), (1, 7161), (1, 7213)} <= lines


def test_short_time_7459_time_margin(conn, main_run):
    """Scenario: 40 kA 1초 요구, 3초 제품 / 시간 여유 제안 포인트."""
    [j] = judgments_at(conn, main_run, 1, 7459)
    assert (j["result"], j["product_code"], j["margin_kind"], float(j["margin_value"]),
            j["margin_direction"]) == ("COMPLY", "GIS-145", "TIME_RATIO", 3, "STRENGTH")
    points = [p for p in queries.run_proposals(conn, main_run)
              if p["judgment_id"] == j["judgment_id"]]
    assert len(points) == 1 and "GIS-145" in points[0]["basis"]


def test_not_strength_margin_7439(conn, main_run):
    """Scenario: 강점이 아닌 여유 — 준수이고 여유가 있어도 제안 포인트를 만들지 않는다."""
    [j] = judgments_at(conn, main_run, 1, 7439)
    assert (j["result"], j["margin_direction"]) == ("COMPLY", "NOT_STRENGTH")
    assert not [p for p in queries.run_proposals(conn, main_run)
                if p["judgment_id"] == j["judgment_id"]]


def test_bundle_c_documents_not_judged(conn, main_run):
    """Scenario: 묶음 C 문서 — 파일 13(미국 규격)에는 판정이 없다."""
    files = {loc["file_no"] for j in _current_judgments(conn, main_run) for loc in j["locations"]}
    assert 13 not in files and 18 not in files and 1 in files


def test_gas_leakage_deviation_linked_to_query(conn, main_run):
    """Scenario: 154 kV 가스 누설 — 0.5 % 일탈과 0.5 % / 1 % 질의가 서로 연결된다."""
    [j] = judgments_at(conn, main_run, 6, 174)
    assert (j["product_code"], j["result"]) == ("GIS-170", "DEVIATION_CANDIDATE")
    outputs = {i["item_id"]: i for i in queries.run_outputs(conn, main_run)}
    [deviation] = [i for i in outputs.values() if i["list_kind"] == "DEVIATION"
                   and any(s["judgment_id"] == j["judgment_id"] for s in i["sources"])]
    linked = [outputs[x] for x in deviation["linked_items"]]
    assert [i["list_kind"] for i in linked] == ["QUERY"]


def test_manufacturer_fixed_value(conn, main_run):
    """Scenario: 회사 고정값 — TS-115-GIS 1번 Manufacturer's name은 LS ELECTRIC."""
    rows = [w for w in _all(queries.run_warranty, conn, main_run)
            if (1, 7431) in {(loc["file_no"], loc["line_start"]) for loc in w["locations"]}]
    assert [(w["candidate_value"], w["source_kind"]) for w in rows] == [("LS ELECTRIC", "FIXED")]


def test_loss_evaluation_case_5(conn, main_run):
    """Scenario: 사례 5 / 손실값 없음 — 360 MVA 변압기는 1,240,400 $(팀 가정),
    나머지는 확인 필요."""
    losses = queries.run_losses(conn, main_run)
    done = [x for x in losses if x["status"] == "CALCULATED"]
    assert [(x["product_code"], float(x["total_usd"]), x["is_assumed"]) for x in done] == [
        ("TRF-HV-230-360A", 1_240_400, True)]
    assert done[0]["locations"][0]["line_start"] == 8238
    rest = [x for x in losses if x["status"] != "CALCULATED"]
    assert rest and all(x["reason_code"] == "NO_LOSS_VALUE" and x["total_usd"] is None
                        for x in rest)
    [point] = [p for p in queries.run_proposals(conn, main_run) if p["point_kind"] == "LOSS"]
    assert point["is_assumed"] and point["text_draft"].endswith("(팀 가정)")


def test_engineering_check_230kv_breaker(conn, main_run):
    """Scenario: 230 kV 차단기 (파일 1 TS-230-GIS II) — 차단 50 kA, 최대 순간 100 kA, 50 Hz이면
    위반(계산값 125)이고 질의 후보가 된다. 115 kV GIS 40 kA·100 kA는 통과."""
    checks = queries.run_checks(conn, main_run)
    [bad] = [c for c in checks if c["result"] == "VIOLATION"]
    assert (float(bad["ik_ka"]), float(bad["peak_ka"]), float(bad["expected_ka"])) == (50, 100, 125)
    assert (1, 7180) in {(loc["file_no"], loc["line_start"]) for loc in bad["locations"]}
    gis_115 = [c for c in checks if c["locations"][0]["table_name"] == "TS-115-GIS"
               and float(c["peak_ka"]) == 100 and c["peak_item_key"] == "peak_current"]
    assert gis_115 and all(c["result"] == "PASS" for c in gis_115)
    assert any(any(s["check_id"] == bad["check_id"] for s in i["sources"])
               for i in queries.run_outputs(conn, main_run, "QUERY"))


def test_field_history_heater(conn):
    """Scenario: 결로 방지 히터 (파일 4 327행) — 고압 개폐기 요구가 FLT-051과 이어지고,
    문장에는 고장 사전의 증상·원인·조치 외 내용이 없다."""
    run_id = run(conn, [4])
    points = [p for p in queries.run_proposals(conn, run_id) if p["point_kind"] == "FIELD"]
    heater = next(p for p in points if "FLT-051" in p["text_draft"])
    assert heater["requirement_id"] == requirement_at(conn, run_id, 4, 327)["requirement_id"]
    assert ("Moisture condensed because the anti-condensation heater was switched off"
            in heater["text_draft"])
    assert "Switch the heater back on and clean the insulators" in heater["text_draft"]
    assert heater["number_check"] == "OK" and heater["product_code"] is None


def test_switch_breaker_product_fills_weight(conn, main_run):
    """Scenario: 제품표 값 / 고를 수 없는 행 — TS-SG 무게는 처음엔 확인 필요, VCB-SUSOL-24-40-3150을
    고르면 318 kg. (실행 상태를 바꾸므로 이 파일의 마지막 테스트로 둔다.)"""
    from rfp_agent.pipeline.run import RunContext, switch_product

    def weight():
        [w] = [w for w in _all(queries.run_warranty, conn, main_run)
               if (1, 11366) in {(loc["file_no"], loc["line_start"]) for loc in w["locations"]}]
        return w

    before = weight()
    assert (before["status"], before["reason_code"]) == ("EMPTY_REVIEW", "PRODUCT_AMBIGUOUS")
    switch_product(RunContext(conn, "test", None, None), main_run, before["equipment_group"],
                   "VCB-SUSOL-24-40-3150")
    after = weight()
    assert (after["candidate_value"], after["candidate_unit"], after["pm_column"]) == (
        "318", "kg", "weight_kg")
