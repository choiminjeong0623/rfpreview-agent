"""판정 정답지·신뢰 구간·재현 채점 명령 (change add-eval-demo, 명세 evaluation)."""

import csv
import os
from pathlib import Path

import pytest

from rfp_agent.config import get_settings
from rfp_agent.db import cli, eval_demo
from rfp_agent.pipeline import evaluation, judge_eval
from rfp_agent.pipeline.run import RunContext, create_run, execute_run

VERSION = "test-dict-v1"
HEAD = ["번호", "text", "expected", "product_code", "ambiguous", "note"]
FILE_28 = get_settings().docx_dir / cli.DEMO_FILE


@pytest.fixture
def run(db, spec):
    run_id = create_run(db, VERSION, None)
    assert execute_run(RunContext(db, VERSION, None, None), run_id, [spec]) == "ENGINEER_REVIEW"
    return run_id


def write_csv(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(HEAD)
        w.writerows(rows)
    return path


def four_judgments(db, run_id):
    """글자가 다른 지금 판정 4줄 (원문, 비교 제품)."""
    rows = db.execute(
        """SELECT DISTINCT ON (q.text_raw) j.judgment_id, q.text_raw, j.product_code
             FROM judgment j JOIN requirement q USING (requirement_id)
            WHERE j.run_id = %s AND j.is_current AND j.product_code IS NOT NULL
            ORDER BY q.text_raw, q.requirement_id LIMIT 4""", (run_id,)).fetchall()
    assert len(rows) == 4
    return rows


def set_result(db, judgment_id, result):
    db.execute("UPDATE judgment SET result = %s, margin_direction = 'NOT_CALC' "
               "WHERE judgment_id = %s", (result, judgment_id))


def test_load_judge_key(db, tmp_path):
    """Scenario: 판정 정답지 넣기 — 4줄, 애매함 1줄, 대상 문서, 일탈 줄의 비교 제품 코드."""
    path = write_csv(tmp_path / "judge.csv", [
        [1, "a / Rated voltage / kV / ≥170 kV", "COMPLY", "GIS-170-50", "", ""],
        [2, "b / Rated current / A / ≥3150 A", "COMPLY", "GIS-170-50", "", ""],
        [3, "c / Service life / years / ≥35 years", "DEVIATION_CANDIDATE", "GIS-170-50", "", ""],
        [4, "d / Breaking time / ms / ≤60 ms", "NEEDS_REVIEW", "", "Y", "후보 여럿"],
    ])
    report = judge_eval.load_judge_key(db, path, "판정 시험", "합성 문서")
    assert (report.rows, report.skipped) == (4, [])
    [key] = [k for k in evaluation.keys(db) if k["key_name"] == "판정 시험"]
    assert (key["key_kind"], key["rows"], key["ambiguous"], key["doc_name"], key["made_by"]) == \
        ("JUDGE", 4, 1, "합성 문서", "CLAUDE_DRAFT")
    product = db.execute("SELECT product_code FROM answer_key_row WHERE key_id = %s AND row_no = 3",
                         (key["key_id"],)).fetchone()[0]
    assert product == "GIS-170-50"


def test_bad_judgment_value(db, tmp_path):
    """Scenario: 잘못된 판정 값 — 그 줄은 빠지고 줄 번호가 알려짐."""
    path = write_csv(tmp_path / "judge.csv", [
        [1, "a / Rated voltage / kV / ≥170 kV", "COMPLY", "", "", ""],
        [2, "b / Rated current / A / ≥3150 A", "PASS", "", "", ""],
    ])
    report = judge_eval.load_judge_key(db, path, "판정 시험", None)
    assert report.rows == 1 and report.skipped == ["2번: 판정 값이 아닙니다 (PASS)"]


def test_judge_key_score(db, run, tmp_path):
    """Scenario: 판정 정답지 채점 — K5-정답지 2/3, K6-정답지 1/1, 애매한 줄 따로, 혼동표."""
    (a, ta, pa), (b, tb, pb), (c, tc, pc), (d, td, _) = four_judgments(db, run)
    set_result(db, a, "COMPLY")
    set_result(db, b, "NEEDS_REVIEW")                 # 정답 준수를 확인 필요로 냄
    set_result(db, c, "DEVIATION_CANDIDATE")
    db.commit()
    path = write_csv(tmp_path / "judge.csv", [
        [1, ta, "COMPLY", pa, "", ""], [2, tb, "COMPLY", pb, "", ""],
        [3, tc, "DEVIATION_CANDIDATE", pc, "", ""], [4, td, "NEEDS_REVIEW", "", "Y", ""]])
    key = judge_eval.load_judge_key(db, path, "판정 시험", None).key_id
    result = evaluation.score(db, [run], judge_key_id=key)
    items = {m["code"]: m for m in result["metrics"]["items"]}
    assert (items["K5-KEY"]["num"], items["K5-KEY"]["den"]) == (2, 3)
    assert (items["K6-KEY"]["num"], items["K6-KEY"]["den"]) == (1, 1)
    detail = result["metrics"]["judgments"]
    assert detail["ambiguous"] == 1
    assert {"expected": "COMPLY", "system": "NEEDS_REVIEW", "count": 1} in detail["table"]
    assert result["judge_key_id"] == key and result["judge_key_name"] == "판정 시험"


def test_judge_key_other_product(db, run, tmp_path):
    """Scenario: 다른 비교 제품 — 판정이 같아도 비교 제품이 다르면 맞지 않음."""
    (a, ta, _), *_ = four_judgments(db, run)
    set_result(db, a, "DEVIATION_CANDIDATE")
    db.commit()
    path = write_csv(tmp_path / "judge.csv", [[1, ta, "DEVIATION_CANDIDATE", "OTHER-1", "", ""]])
    key = judge_eval.load_judge_key(db, path, "판정 시험", None).key_id
    m = evaluation.metrics(db, [run], None, None, key)
    k5 = next(x for x in m["items"] if x["code"] == "K5-KEY")
    assert (k5["num"], k5["den"]) == (0, 1)


def test_wilson_small_sample():
    """Scenario: 작은 표본의 구간 — 4/4의 아래 값(약 51 %)이 65/65(약 94 %)보다 낮다."""
    assert evaluation.wilson(4, 4) == (51.0, 100.0)
    assert evaluation.wilson(65, 65) == (94.4, 100.0)
    assert evaluation.wilson(0, 0) is None
    m = evaluation._metric("K1", "이름", "잼", "%", 100.0, 4, 4)
    assert (m["ci_low"], m["ci_high"]) == (51.0, 100.0)
    assert evaluation._metric("K11", "이름", "잼", "건", 0)["ci_low"] is None


def test_synthetic_deviation_script(tmp_path):
    """Scenario: 스크립트로 합성 RFP 만들기 — 파일 25 부록 B 표 TS-170-GIS에 D-01~D-11."""
    from docx import Document

    name = "RFP_Product_Master_Evaluative_EN_With_Deviation_Candidates.docx"
    path = get_settings().docx_dir / name
    if not path.exists():
        pytest.skip("파일 25 없음 — " + cli.MAKE_SYNTHETIC)
    doc = Document(str(path))
    tables = [t for t in doc.tables if t.rows[0].cells[0].text.strip() == "TS-170-GIS"]
    assert len(tables) == 2                                   # 4.2와 부록 B
    numbers = [r.cells[0].text.strip() for r in tables[1].rows[2:]]
    assert numbers == [f"D-{i:02d}" for i in range(1, 12)]


@pytest.fixture
def env(db_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("RFP_AI_MODE", os.environ.get("RFP_AI_MODE", "gemini"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.skipif(not FILE_28.exists(), reason="파일 28 없음 — " + cli.MAKE_SYNTHETIC)
def test_eval_demo_same_table(db, env, db_url, tmp_path, monkeypatch):
    """Scenario: 재현 채점 — 같은 표, 정답지 세 개 지표, 처리 시간 없음.

    Scenario: 합성 RFP 정답지 넣기 · 합성 RFP 정답지 채점 (공개본 스크립트로 만든 파일 28).
    """
    from rfp_agent.db.seed import seed_products

    # 시험 DB에는 시험용 제품표가 있다. 빈 DB처럼 실제 제품표로 바꿔 둔다
    seed_products(db, [get_settings().seed_dir / "products" / "product_master.csv"], replace=True)
    db.commit()
    monkeypatch.chdir(tmp_path)
    first = eval_demo.run(False, Path("a.md"), None)
    keys = {k["key_name"]: (k["key_kind"], k["rows"], k["made_by"]) for k in evaluation.keys(db)}
    assert keys == {"합성 RFP 28 요구사항": ("REQ", 69, "HUMAN"),
                    "합성 RFP 28 유형": ("TYPE", 65, "HUMAN"),
                    "합성 RFP 28 판정": ("JUDGE", 30, "CLAUDE_DRAFT")}
    [saved] = evaluation.history(db)
    got = {m["code"]: (m["num"], m["den"]) for m in saved["metrics"]["items"]}
    assert {k: got[k] for k in ("K1", "K2", "K3", "K10", "K13", "K5-KEY", "K6-KEY")} == {
        "K1": (65, 65), "K2": (65, 66), "K3": (30, 30), "K10": (4, 4), "K13": (38, 38),
        "K5-KEY": (29, 30), "K6-KEY": (10, 10)}
    assert "| TIME" not in first and "| K5-KEY |" in first
    assert (tmp_path / "a.md").read_text(encoding="utf-8") == first
    # 다시 돌리면 같은 표: 검토가 있는 DB는 거절하므로 표만 다시 만든다
    again = eval_demo.table(saved["metrics"], [k for k in evaluation.keys(db)],
                            first.split("`")[1])
    assert again == first


@pytest.mark.skipif(not FILE_28.exists(), reason="파일 28 없음")
def test_eval_demo_refuses_db_with_runs(db, env):
    """재현 채점도 검토가 있는 DB는 거절한다(지우지 않음)."""
    create_run(db, VERSION, None)
    db.commit()
    with pytest.raises(SystemExit):
        eval_demo.run(False, None, None)
