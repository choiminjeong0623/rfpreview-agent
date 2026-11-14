"""FR-15 현장 이력 연결. 명세 field-history와 reference-data(고장 사전·연결표 적재)의 Scenario.

합성 문서로 확인한다. 실제 문서(파일 4 327행)로 하는 확인은 test_corpus.py에 있다.
"""

import shutil

import pytest
from docx import Document

from rfp_agent.db.migrate import migrate
from rfp_agent.db.seed import SeedError, seed_rules, suspect_reason
from rfp_agent.pipeline import queries
from rfp_agent.pipeline.field_history import equipment_kind, load_links
from rfp_agent.pipeline.run import RunContext, create_run, execute_run
from tests.conftest import FakeLLM

VERSION = "test-dict-v1"
HEATER = ("결로 방지 히터 요구와 이어지는 현장 고장 FLT-051 (제품군 MV_EQUIP). "
          "증상: Partial discharge alarm raised in switchgear panel. "
          "원인: Moisture condensed because the anti-condensation heater was switched off. "
          "조치: Switch the heater back on and clean the insulators. 해결 사례 4건.")


HEATER_TEXT = ("Anti-condensation heaters shall be provided in each control panel "
               "and shall be controlled by adjustable thermostat.")


def build_switchgear_spec(path, heater: bool = True, heater_text: str = HEATER_TEXT):
    """고압 개폐기 사양서 흉내: 결로 방지 히터 문장, 연결표에 없는 도장 문장, 변압기 히터 문장."""
    doc = Document()
    doc.add_paragraph("SPECIFICATION FOR HIGH VOLTAGE SWITCHGEAR")
    doc.add_paragraph("1. GENERAL")
    doc.add_paragraph("The switchgear shall be indoor type and shall comply with IEC 62271-1.")
    for topic in ("enclosure", "busbar", "earthing", "cable entry", "nameplate"):
        doc.add_paragraph(f"The {topic} shall be as specified in the general specification.")
    doc.add_paragraph("2. LOCAL CONTROL PANEL")
    if heater:
        doc.add_paragraph(heater_text)
    doc.add_paragraph("The final coating of the enclosure shall be as per RAL 7032.")
    doc.add_paragraph("3. AUXILIARY TRANSFORMER")
    doc.add_paragraph("A space heater shall be provided in the transformer control cubicle.")
    doc.save(str(path))
    return path


def run_once(conn, paths, llm=None):
    run_id = create_run(conn, VERSION, llm)
    assert execute_run(RunContext(conn, VERSION, llm, None), run_id, paths) == "ENGINEER_REVIEW"
    return run_id


def field_points(conn, run_id):
    return [p for p in queries.run_proposals(conn, run_id) if p["point_kind"] == "FIELD"]


def test_heater_links_to_flt051(db, tmp_path):
    """Scenario: 결로 방지 히터 / 문장 내용 / 현장 이력 후보 — 고압 개폐기 요구가 FLT-051과
    이어지고, 문장에는 고장 사전의 증상·원인·조치와 해결 사례 수 외 내용이 없다. 후보는 1건이고
    근거는 요구 원문 위치와 연결표 줄이다 (제품 행 없음)."""
    run_id = run_once(db, [build_switchgear_spec(tmp_path / "synthetic_hv_switchgear.docx")])
    [point] = field_points(db, run_id)
    assert point["text_draft"] == HEATER
    assert (point["drafted_by"], point["number_check"], point["status"]) == (
        "CODE", "OK", "CANDIDATE")
    assert point["product_code"] is None and point["fault_link_id"] and point["locations"]
    assert "Anti-condensation" in db.execute(
        "SELECT text_raw FROM requirement WHERE requirement_id = %s",
        (point["requirement_id"],)).fetchone()[0]


def test_other_equipment_is_not_linked(db, tmp_path):
    """Scenario: 설비 종류가 다름 — 변압기 함의 히터는 개폐기 고장과 잇지 않는다."""
    run_id = run_once(db, [build_switchgear_spec(tmp_path / "synthetic_hv_switchgear.docx")])
    [point] = field_points(db, run_id)
    assert "같은 요구 1곳" in point["basis"]


def test_same_fault_in_two_documents_is_one_point(db, tmp_path):
    """Scenario: 같은 고장이 여러 요구에 — 후보는 하나, 앞선 파일 요구가 대표, 요구 수를 적는다."""
    paths = [build_switchgear_spec(tmp_path / "synthetic_hv_switchgear_1.docx"),
             build_switchgear_spec(tmp_path / "synthetic_hv_switchgear_2.docx",
                                   heater_text="An anti-condensation heater shall be fitted in "
                                               "each mechanism box.")]
    run_id = run_once(db, paths)
    [point] = field_points(db, run_id)
    first = min(r[0] for r in db.execute("SELECT file_no FROM document"))
    assert point["locations"][0]["file_no"] == first
    assert "같은 요구 2곳" in point["basis"]


def test_item_not_in_link_table_is_not_linked(db, tmp_path):
    """Scenario: 연결표에 없는 항목 — 연결하지 않는다."""
    path = build_switchgear_spec(tmp_path / "synthetic_hv_switchgear.docx", heater=False)
    run_id = run_once(db, [path])
    assert field_points(db, run_id) == []


def test_field_sentence_is_not_written_by_ai(db, tmp_path):
    """Scenario: 언어 모델이 있어도 — 현장 이력 문장은 코드가 쓰고 AI에 보내지 않는다."""
    llm = FakeLLM(text="초안 {f} 고장은 9999건입니다.")
    run_id = run_once(db, [build_switchgear_spec(tmp_path / "synthetic_hv_switchgear.docx")],
                      llm)
    [point] = field_points(db, run_id)
    assert point["text_draft"] == HEATER and point["drafted_by"] == "CODE"
    assert not any("Moisture condensed" in p for p in llm.prompts)


def test_suspicious_cases_are_not_counted(seeded_db):
    """Scenario: 의심 사례 표시 ·
    Scenario: 의심 사례 — 해결 사례 수에서 뺀다 (FLT-051: 5건 중 1건 의심 → 4건)."""
    link = next(x for x in load_links(seeded_db) if x.fault_id == "FLT-051")
    assert (link.cases, link.suspects) == (4, 1)
    total = seeded_db.execute("SELECT count(*), count(suspect_reason) FROM resolution_case"
                              ).fetchone()
    # 공개본은 운영진 C/S 데이터(800건) 대신 합성 표본 19건을 쓴다 (docs/data.md)
    assert total == (19, 1)


def test_suspect_reasons():
    """Scenario: 의심 이유 ·
    Scenario: 고장 사전과 어긋난 사례 — RMA 번호 불일치, 처리 시간 10배 초과."""
    fault = {"needs_rma": "N", "typical_resolution_hours": "24"}
    normal = {"rma_no": "", "time_to_resolve_hours": "30.0"}
    assert suspect_reason(normal, fault) is None
    odd = {"rma_no": "RMA-1", "time_to_resolve_hours": "311.7"}
    assert suspect_reason(odd, fault) == (
        "RMA 번호 불일치 (사전: RMA 불필요, 사례: RMA-1) / "
        "처리 시간 311.7h (사전 기준 24h의 10배 초과)")
    assert suspect_reason(odd, {**fault, "needs_rma": "Y"}).startswith("처리 시간")


def test_link_table_loaded(seeded_db):
    """Scenario: 연결표 적재 — 팀이 채택한 8줄이 확정자 '팀 확정'으로 들어간다."""
    rows = seeded_db.execute("SELECT item_key, fault_id, confirmed_by, equipment_kinds "
                             "FROM fault_link ORDER BY fault_id").fetchall()
    assert len(rows) == 8 and {r[2] for r in rows} == {"팀 확정"}
    assert ("anti_condensation_heater", "FLT-051", "팀 확정",
            ["GIS", "BREAKER", "SWITCHGEAR"]) in rows


def test_unknown_fault_stops_loading(empty_db, settings, tmp_path):
    """Scenario: 고장 사전에 없는 고장 번호 — 적재를 멈춘다."""
    migrate(empty_db, settings.migrations_dir)
    seed_dir = tmp_path / "seed"
    shutil.copytree(settings.seed_dir, seed_dir)
    links = seed_dir / "fault_link.csv"
    links.write_text(links.read_text(encoding="utf-8").replace("FLT-051", "FLT-999"),
                     encoding="utf-8")
    with pytest.raises(SeedError, match="FLT-999"):
        seed_rules(empty_db, seed_dir)


def test_no_catalog_turns_feature_off(empty_db, settings, tmp_path, db_url):
    """Scenario: 고장 사전 파일 없음 — 현장 이력 표를 비우고 연결하지 않는다."""
    migrate(empty_db, settings.migrations_dir)
    seed_rules(empty_db, settings.seed_dir)
    seed_dir = tmp_path / "seed"
    shutil.copytree(settings.seed_dir, seed_dir)
    for name in ("fault_catalog.csv", "resolution_cases.csv", "fault_link.csv"):
        (seed_dir / name).unlink()
    report = seed_rules(empty_db, seed_dir)
    assert any("FR-15" in line for line in report.skipped)
    assert empty_db.execute("SELECT count(*) FROM fault_link").fetchone()[0] == 0
    assert load_links(empty_db) == []


@pytest.mark.parametrize(("own", "table", "sections", "file", "kind"), [
    ("Anti-condensation heaters shall be provided.", None, ["Local control panel"],
     "Specification for High Voltage Switchgear", "SWITCHGEAR"),
    ("Space heater for transformer control cubicle", "TS-SG", [], "", "TRANSFORMER"),
    ("- Switchgear space heater", "TS-SG", [], "", "SWITCHGEAR"),
    ("Buchholz relay", "TS-AUTO-TR", [], "", "TRANSFORMER"),
    ("Type of operating mechanism", "TS-230-GIS", [], "", "GIS"),
    ("Spring charge mechanism", "TS-115-CB", [], "", "BREAKER"),
    ("The polarity of current transformers shall be checked.", None, [], "", "INSTRUMENT"),
    ("Paint shall be RAL 7032.", None, ["Painting"], "General", None),
])
def test_equipment_kind(own, table, sections, file, kind):
    """설비 종류는 요구 문장 → 표 이름 → 절 제목 → 문서 이름 순서로 찾는다."""
    assert equipment_kind(own, table, None, sections, file) == kind
