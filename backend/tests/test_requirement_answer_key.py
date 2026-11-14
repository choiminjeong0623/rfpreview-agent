"""요구사항 정답지로 K1·K2·K3·K10 재기 (change add-requirement-answer-key, 명세 evaluation)."""

import csv
from pathlib import Path

import pytest
from docx import Document

from rfp_agent.db.cli import main as rfp_db
from rfp_agent.pipeline import evaluation, req_eval
from rfp_agent.pipeline.review import ReviewError
from rfp_agent.pipeline.run import RunContext, create_run, execute_run
from tests.docx_factory import build_gis_spec

VERSION = "test-dict-v1"
SYNTHETIC_KEY = (Path(__file__).parents[2] / "data" / "seed" / "answer_keys"
                 / "synthetic_154kV_GIS_req.csv")
HEAD = ["번호", "text", "expected", "value", "unit", "note"]


def write_csv(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(HEAD)
        w.writerows(rows)
    return path


def metric(result, code):
    return next(m for m in result["metrics"]["items"] if m["code"] == code)


def fraction(result, code):
    m = metric(result, code)
    return m["num"], m["den"]


@pytest.fixture
def gis_run(db, tmp_path):
    """합성 154 kV GIS 문서만 든 검토 (판정하지 않는 묶음 C → 판정 줄 0)."""
    path = build_gis_spec(tmp_path / "synthetic_154kV_GIS_spec.docx")
    run_id = create_run(db, VERSION, None)
    assert execute_run(RunContext(db, VERSION, None, None), run_id, [path]) == "ENGINEER_REVIEW"
    return run_id


def load(db, path, name="합성 154kV", doc="synthetic_154kV_GIS"):
    return req_eval.load_req_key(db, path, name, doc)


def test_load_requirement_key(db, tmp_path):
    """Scenario: 합성 문서 정답지 넣기 — 요구사항 정답지 4줄, 대상 문서, 값·단위 저장."""
    path = write_csv(tmp_path / "key.csv", [
        [1, "Rated voltage", "REQUIREMENT", "170", "kV", ""],
        [2, "Type Test Report", "requirement", "", "", ""],
        [3, "The switchgear shall comply with IEC 62271-203.", "REQUIREMENT", "", "", ""],
        [4, "Any item not listed shall be deemed to be accepted.", "BLANKET", "", "", "포괄"],
    ])
    report = load(db, path, "합성")
    assert (report.rows, report.skipped) == (4, [])
    [key] = [k for k in evaluation.keys(db) if k["key_name"] == "합성"]
    assert (key["key_kind"], key["rows"], key["doc_name"], key["made_by"]) == (
        "REQ", 4, "synthetic_154kV_GIS", "CLAUDE_DRAFT")
    value = db.execute("SELECT value_raw, unit_raw FROM answer_key_row "
                       "WHERE key_id = %s AND row_no = 1", (key["key_id"],)).fetchone()
    assert value == ("170", "kV")


def test_load_requirement_key_cli(db, tmp_path, db_url, monkeypatch):
    """명령 `rfp-db load-answer-key … --kind REQ --doc …`로도 넣는다."""
    from rfp_agent.config import get_settings

    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    try:
        rfp_db(["load-answer-key", str(SYNTHETIC_KEY), "--name", "합성 CLI", "--kind", "REQ",
                "--doc", "synthetic_154kV_GIS"])
    finally:
        get_settings.cache_clear()
    [key] = [k for k in evaluation.keys(db) if k["key_name"] == "합성 CLI"]
    assert (key["key_kind"], key["rows"]) == ("REQ", 19)


def test_bad_expected_kind(db, tmp_path):
    """Scenario: 잘못된 정답 종류 — 그 줄은 빠지고 줄 번호가 알려진다."""
    path = write_csv(tmp_path / "bad.csv", [
        [1, "Rated voltage", "REQUIREMENT", "170", "kV", ""],
        [2, "Rated normal current", "COST_SHIFT", "", "", ""],
    ])
    report = load(db, path)
    assert report.rows == 1
    assert report.skipped == ["2번: 정답 종류가 아닙니다 (COST_SHIFT)"]


def build_supplier_answer(path: Path, header: bool = True) -> Path:
    """공급사 답안 모양: 표시 머리, 표시 칸이 있는 조항, 병합 칸에 표시가 쌓인 조항, 제목 줄."""
    doc = Document()
    table = doc.add_table(rows=5, cols=3)
    rows = [
        ["SECTION 26", "C: Complied D: Deviation E: Exclusion" if header else "SECTION", ""],
        ["C", "A.", "Equipment shall be designed for outdoor service."],
        ["D", "B.", "Cabinets shall be rated NEMA 3R with padlock."],
        ["", "", "QUALITY ASSURANCE"],
        ["", "C.", "Installation shall follow the manufacturer instructions."],
    ]
    for tr, values in zip(table.rows, rows, strict=True):
        for cell, value in zip(tr.cells, values, strict=True):
            cell.text = value
    merged = table.cell(3, 0).merge(table.cell(4, 0))   # 병합 칸에 표시가 쌓임
    merged.text = "C\nE"
    doc.save(str(path))
    return path


def test_supplier_key_from_marked_tables(db, tmp_path):
    """Scenario: 표시 표의 조항 줄 — 조항 3줄, 제목 줄 없음, 앞 2줄 메모에 표시, 코드 자동."""
    path = build_supplier_answer(tmp_path / "supplier answer.docx")
    report = req_eval.make_supplier_key(db, path, "공급사 답안")
    assert report.rows == 3
    rows = db.execute("SELECT text_raw, expected, note FROM answer_key_row WHERE key_id = %s "
                      "ORDER BY row_no", (report.key_id,)).fetchall()
    assert rows == [
        ("Equipment shall be designed for outdoor service.", "REQUIREMENT", "공급사 표시 C"),
        ("Cabinets shall be rated NEMA 3R with padlock.", "REQUIREMENT", "공급사 표시 D"),
        ("Installation shall follow the manufacturer instructions.", "REQUIREMENT", None),
    ]
    [key] = [k for k in evaluation.keys(db) if k["key_name"] == "공급사 답안"]
    assert (key["made_by"], key["doc_name"], key["key_kind"]) == ("AUTO", "supplier answer",
                                                                   "REQ")


def test_supplier_key_needs_mark_header(db, tmp_path):
    """Scenario: 표시 머리가 없는 문서 — 정답지를 만들지 않고 알린다."""
    path = build_supplier_answer(tmp_path / "plain.docx", header=False)
    with pytest.raises(ReviewError, match="공급사 답안 문서가 아닙니다"):
        req_eval.make_supplier_key(db, path, "공급사 답안")
    assert not [k for k in evaluation.keys(db) if k["key_name"] == "공급사 답안"]


def test_extraction_recall_and_precision(db, gis_run, tmp_path):
    """Scenario: 추출 재현율과 정확도.

    합성 문서 정답지 전체로 K1·K2가 16/16. 정답지에서 한 줄을 빼면 그 줄은 K2 분모에만 든다.
    """
    full = load(db, SYNTHETIC_KEY)
    result = evaluation.score(db, [gis_run], req_key_id=full.key_id)
    assert fraction(result, "K1") == (16, 16)
    assert fraction(result, "K2") == (16, 16)
    assert result["req_key_name"] == "합성 154kV"
    assert "K1" not in {m["code"] for m in result["metrics"]["not_measured"]}
    assert result["metrics"]["requirements"]["documents"] == 1

    with SYNTHETIC_KEY.open(encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f) if r["번호"] != "1"]
    path = write_csv(tmp_path / "less.csv", [[r[h] for h in HEAD] for r in rows])
    less = load(db, path, "한 줄 뺌")
    result = evaluation.score(db, [gis_run], req_key_id=less.key_id)
    assert fraction(result, "K1") == (15, 15)
    assert fraction(result, "K2") == (15, 16)


def test_value_unit_accuracy_without_conversion(db, gis_run, tmp_path):
    """Scenario: 값·단위 정확도 — 40 kA는 맞고, 170000 V는 170 kV로 바꿔 맞추지 않는다."""
    path = write_csv(tmp_path / "values.csv", [
        [1, "Rated short-time withstand current, (1 sec.)", "REQUIREMENT", "40", "kA", ""],
        [2, "Rated voltage", "REQUIREMENT", "170000", "V", "단위가 다름"],
    ])
    key = load(db, path, "값")
    result = evaluation.score(db, [gis_run], req_key_id=key.key_id)
    assert fraction(result, "K3") == (1, 2)
    assert fraction(result, "K1") == (2, 2)

    full = load(db, SYNTHETIC_KEY)
    assert fraction(evaluation.score(db, [gis_run], req_key_id=full.key_id), "K3") == (12, 12)


def test_risk_detection_recall(db, gis_run):
    """Scenario: 위험 조건 탐지 재현율 — 포괄 조항·범위 모호·값 불일치 3줄을 모두 찾음."""
    key = load(db, SYNTHETIC_KEY)
    result = evaluation.score(db, [gis_run], req_key_id=key.key_id)
    assert fraction(result, "K10") == (3, 3)
    assert metric(result, "K10")["passed"] is True


def test_unjudged_run_can_be_scored(db, gis_run):
    """Scenario: 판정 없는 검토 채점 — 판정 줄 0으로 목록에 보이고 K1·K2가 재진다."""
    [row] = [r for r in evaluation.candidate_runs(db) if r["run_id"] == gis_run]
    assert row["reviewed"] == 0
    key = load(db, SYNTHETIC_KEY)
    result = evaluation.score(db, [gis_run], req_key_id=key.key_id)
    assert metric(result, "K1")["value"] == 100.0
    assert metric(result, "K5")["value"] is None          # 판정 줄이 없어 분모 0


def test_key_kinds_are_checked(db, gis_run, tmp_path):
    """유형 정답지 자리에 요구사항 정답지를 주면 거절한다."""
    key = load(db, SYNTHETIC_KEY)
    with pytest.raises(ReviewError, match="유형 정답지가 아닙니다"):
        evaluation.score(db, [gis_run], key_id=key.key_id)


def test_same_line_rules():
    """글자 맞추기: 같음, 30자 이상 품음, 표 줄 칸 하나와 같음. 짧은 글자는 품어도 다름."""
    same = req_eval.same_line
    n = req_eval.normalize
    assert same(n("Rated voltage"), n("1 / Rated voltage / kV / 170"))
    assert not same(n("Rated voltage"), n("4 / Rated voltage of auxiliary circuits / V / x"))
    assert same(n("The switchgear shall comply with IEC 62271-203"),
                n("1.2 The switchgear shall comply with IEC 62271-203 and IEC 62271-1."))
    assert not same(n("shall comply"), n("The switchgear shall comply with IEC."))
