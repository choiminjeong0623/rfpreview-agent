"""정답지·채점 (change add-evaluation, 명세 evaluation)."""

import csv

import pytest

from rfp_agent.db.cli import main as rfp_db
from rfp_agent.pipeline import evaluation, review
from rfp_agent.pipeline.run import RunContext, create_run, execute_run

VERSION = "test-dict-v1"
HEAD = ["번호", "requirement_id", "text", "context", "Claude초안", "애매함(Y)", "이유",
        "사람 확인(맞으면 비움, 다르면 코드)"]


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


def act(db, run_id, judgment_id, action, value=None, reason=None):
    review.act(RunContext(db, VERSION, None, None), run_id, "judgment", judgment_id, action,
               value, reason)


def comply_ids(db, run_id, n):
    ids = [r[0] for r in db.execute(
        "SELECT judgment_id FROM judgment WHERE run_id = %s AND is_current AND result = 'COMPLY' "
        "ORDER BY judgment_id LIMIT %s", (run_id, n))]
    assert len(ids) == n
    return ids


def metric(result, code):
    return next(m for m in result["metrics"]["items"] if m["code"] == code)


def test_load_claude_draft(db, tmp_path, db_url, monkeypatch):
    """Scenario: Claude 초안 정답지 넣기 — 4줄, 사람 확인 1줄, 사람 값이 정답."""
    path = write_csv(tmp_path / "key.csv", [
        [1, "", "The GIS shall be type tested.", "1 절", "TEST", "", "", ""],
        [2, "", "Rated voltage 170 kV.", "표", "TECH_PERF", "", "", ""],
        [3, "", "Delay penalty applies.", "계약", "TECH_PERF", "Y", "애매", "COST"],
        [4, "", "General description.", "", "NONE", "", "", ""],
    ])
    from rfp_agent.config import get_settings

    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    try:
        rfp_db(["load-answer-key", str(path), "--name", "유형 초안"])
    finally:
        get_settings.cache_clear()
    [key] = evaluation.keys(db)
    assert (key["key_name"], key["rows"], key["human_checked"], key["made_by"]) == \
        ("유형 초안", 4, 1, "CLAUDE_DRAFT")
    assert key["ambiguous"] == 1
    assert db.execute("SELECT expected, human_checked FROM answer_key_row "
                      "WHERE key_id = %s AND row_no = 3", (key["key_id"],)).fetchone() == \
        ("COST", True)
    # 같은 이름으로 다시 넣으면 줄을 바꾼다
    evaluation.load_key(db, write_csv(tmp_path / "k2.csv", [[1, "", "x", "", "RISK", "", "", ""]]),
                        "유형 초안")
    assert [k["rows"] for k in evaluation.keys(db)] == [1]


def test_bad_type_code(db, tmp_path):
    """Scenario: 잘못된 유형 코드 — 그 줄은 빠지고 줄 번호가 알려진다."""
    path = write_csv(tmp_path / "bad.csv", [
        [1, "", "a shall be b.", "", "TEST", "", "", ""],
        [2, "", "c shall be d.", "", "PRICE", "", "", ""],
    ])
    report = evaluation.load_key(db, path, "잘못")
    assert report.rows == 1
    assert len(report.skipped) == 1 and report.skipped[0].startswith("2번")


def test_judgment_accuracy_from_human(db, run):
    """Scenario: 사람 확정 기준 판정 정확도 — 3줄 확정, 1줄 준수→일탈 수정이면 K5 3/4, K6 0/1."""
    a, b, c, d = comply_ids(db, run, 4)
    for j in (a, b, c):
        act(db, run, j, "CONFIRM")
    act(db, run, d, "EDIT", {"result": "DEVIATION_CANDIDATE"}, "값이 다름")
    result = evaluation.score(db, [run])
    k5, k6 = metric(result, "K5"), metric(result, "K6")
    assert (k5["num"], k5["den"], k5["value"]) == (3, 4, 75.0)
    assert (k6["num"], k6["den"], k6["value"]) == (0, 1, 0.0)
    assert k5["passed"] is False and k5["target"] == 80.0


def test_type_accuracy(db, run, tmp_path):
    """Scenario: 유형 분류 정확도 — 같은 글자 3줄(2줄 정답)과 없는 줄 1개면 K13 2/3, 못 찾음 1."""
    reqs = db.execute(
        """SELECT q.text_raw, coalesce(t.type_code, 'NONE') FROM requirement q
             LEFT JOIN requirement_type_tag t ON t.requirement_id = q.requirement_id
                                             AND t.is_primary
            WHERE q.req_kind = 'REQUIREMENT' AND q.document_id IN
                  (SELECT document_id FROM run_document WHERE run_id = %s)
            ORDER BY q.requirement_id""", (run,)).fetchall()
    seen, picked = set(), []
    for text, code in reqs:                 # 글자가 겹치지 않는 줄 3개
        if evaluation.normalize(text) not in seen:
            seen.add(evaluation.normalize(text))
            picked.append((text, code))
        if len(picked) == 3:
            break
    wrong = "RISK" if picked[2][1] != "RISK" else "COST"
    rows = [[1, "", "  " + picked[0][0].upper() + " ", "", picked[0][1], "", "", ""],
            [2, "", picked[1][0], "", picked[1][1], "", "", ""],
            [3, "", picked[2][0], "", wrong, "", "", ""],
            [4, "", "이 문장은 문서에 없습니다.", "", "TEST", "", "", ""]]
    key = evaluation.load_key(db, write_csv(tmp_path / "t.csv", rows), "유형").key_id
    act(db, run, comply_ids(db, run, 1)[0], "CONFIRM")
    result = evaluation.score(db, [run], key)
    k13 = metric(result, "K13")
    assert (k13["num"], k13["den"]) == (2, 3)
    assert result["metrics"]["types"]["not_found"] == 1
    assert "못 찾은 줄 1개" in k13["note"]


def test_result_only_metrics(db, run):
    """Scenario: 결과만으로 재는 지표 — K4 100 %, K11·K12 0건, 처리 시간(분)."""
    act(db, run, comply_ids(db, run, 1)[0], "CONFIRM")
    result = evaluation.score(db, [run])
    assert metric(result, "K4")["value"] == 100.0
    assert metric(result, "K11")["value"] == 0 and metric(result, "K12")["value"] == 0
    time = metric(result, "TIME")
    assert time["unit"] == "분" and time["value"] is not None and time["value"] >= 0
    assert {m["code"] for m in result["metrics"]["not_measured"]} == \
        {"K1", "K2", "K3", "K8", "K9", "K10"}


def test_same_input_same_score(db, run):
    """Scenario: 같은 입력 같은 점수 (CR-11)."""
    a, b = comply_ids(db, run, 2)
    act(db, run, a, "CONFIRM")
    act(db, run, b, "EDIT", {"result": "QUERY_CANDIDATE"}, "확인")
    first, second = evaluation.score(db, [run]), evaluation.score(db, [run])
    assert first["metrics"] == second["metrics"]


def test_before_after(db, run, db_url, monkeypatch):
    """Scenario: 개선 전후 — 두 기록이 최근 것부터, 두 번째에 메모와 바뀐 K5."""
    a, b = comply_ids(db, run, 2)
    act(db, run, a, "CONFIRM")
    evaluation.score(db, [run])
    act(db, run, b, "EDIT", {"result": "DEVIATION_CANDIDATE"}, "값이 다름")

    from fastapi.testclient import TestClient

    from rfp_agent.api.main import app
    from rfp_agent.config import get_settings

    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    try:
        client = TestClient(app)
        res = client.post("/api/eval/scores", json={"run_ids": [run], "note": "비교 규칙 고침"})
        assert res.status_code == 200, res.text
        rows = client.get("/api/eval/scores").json()
        assert [r["note"] for r in rows] == ["비교 규칙 고침", None]
        k5 = [metric(r, "K5")["value"] for r in rows]
        assert k5 == [50.0, 100.0]
        assert [r["run_id"] for r in client.get("/api/eval/runs").json()] == [run]
        assert client.post("/api/eval/scores", json={"run_ids": [9999]}).status_code == 404
    finally:
        get_settings.cache_clear()
