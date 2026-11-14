"""요약 상자 문장 (change add-screen-summary, 결정 Q1).

명세 review-workspace "요약 문장은 코드가 쓴다"·"검토 요약"·"홈 요약"의 Scenario.
문장은 코드가 틀에 숫자·이름·날짜를 채운다. 언어 모델은 부르지 않는다.
"""

from datetime import date, timedelta

from rfp_agent.pipeline import doc_add, queries, review, screen_summary
from rfp_agent.pipeline.run import RunContext, create_run, execute_run
from rfp_agent.pipeline.screen_summary import day_text, home_summary, review_summary
from tests.docx_factory import build_gis_spec

VERSION = "test-dict-v1"


def ctx(conn):
    return RunContext(conn, VERSION, None, None)


def user(conn, role):
    return conn.execute("SELECT min(user_id) FROM app_user WHERE role = %s", (role,)).fetchone()[0]


def finished(conn, spec):
    run_id = create_run(conn, VERSION, None)
    assert execute_run(ctx(conn), run_id, [spec]) == "ENGINEER_REVIEW"
    return run_id


def text(sentence):
    return "".join(p["t"] for p in sentence)


def set_results(conn, run_id, results):
    """판정 줄을 앞에서부터 results 값으로 고친다. 나머지는 준수."""
    ids = [i for (i,) in conn.execute(
        "SELECT judgment_id FROM judgment WHERE run_id = %s AND is_current ORDER BY judgment_id",
        (run_id,))]
    assert len(ids) >= len(results)
    eng = user(conn, "ENGINEER")
    for jid, res in zip(ids, results + ["COMPLY"] * (len(ids) - len(results)), strict=True):
        review.act(ctx(conn), run_id, "judgment", jid, "EDIT", {"result": res}, "테스트", eng)
    return ids


def test_same_data_same_sentences(db, spec, monkeypatch):
    """Scenario: 같은 데이터면 같은 문장 / AI를 부르지 않음 —
    언어 모델이 없어도, 두 번 불러도 같다."""
    run_id = finished(db, spec)

    def no_llm(*a, **k):
        raise AssertionError("요약은 언어 모델을 부르지 않는다")

    monkeypatch.setattr("rfp_agent.llm.client.make_llm", no_llm)
    a, b = review_summary(db, run_id), review_summary(db, run_id)
    assert a["sentences"] and a["sentences"] == b["sentences"]
    assert a["written_by"] == "CODE" and a["meta"].startswith("문서 1개에서 요구사항")
    assert home_summary(db, None)["sentences"] == home_summary(db, None)["sentences"]


def test_must_see_and_submit_by(db, spec):
    """Scenario: 꼭 볼 판정과 상신 권장일 — 탭 수와 같은 수, 상신 권장일(마감 2일 전)은 강조."""
    run_id = finished(db, spec)
    set_results(db, run_id, ["DEVIATION_CANDIDATE", "DEVIATION_CANDIDATE", "QUERY_CANDIDATE",
                             "NEEDS_REVIEW", "NEEDS_REVIEW", "NEEDS_REVIEW"])
    due = date.today() + timedelta(days=10)
    db.execute("UPDATE review_run SET due_date = %s WHERE run_id = %s", (due, run_id))
    s = review_summary(db, run_id)["sentences"]
    must = next(x for x in s if text(x).startswith("꼭 볼 것"))
    by = day_text(due - timedelta(days=2))
    assert text(must) == (f"꼭 볼 것 6줄은 일탈 후보 2건, 질의 후보 1건, 확인 필요 3건입니다. "
                          f"상신 권장일은 {by}입니다.")
    assert {"t": by, "kind": "strong", "href": None} in must


def test_first_deviations_link(db, spec):
    """Scenario: 먼저 볼 일탈 후보 링크 — 두 줄이 판정 상세 링크, 나머지는 "외 n건"."""
    run_id = finished(db, spec)
    ids = set_results(db, run_id, ["DEVIATION_CANDIDATE"] * 3)
    s = review_summary(db, run_id)["sentences"]
    dev = next(x for x in s if text(x).startswith("먼저 볼 일탈 후보"))
    links = [p for p in dev if p["kind"] == "link"]
    assert [p["href"] for p in links] == [f"/reviews/{run_id}/judgments/{i}" for i in ids[:2]]
    assert text(dev).endswith(" 외 1건입니다.")


def test_revision_and_empty_cells(db, spec, tmp_path, monkeypatch):
    """Scenario: 개정과 빈 작성 칸 — "바뀐 줄 보기"(?rev=1)와 "데이터시트 채우기" 링크."""
    run_id = finished(db, spec)
    extra = build_gis_spec(tmp_path / "addendum_gis.docx")
    paths, merged = doc_add.prepare_add(db, run_id, [extra], {extra.name: {"bundle": "A"}},
                                        user(db, "ENGINEER"))
    assert execute_run(ctx(db), run_id, paths, merged) == "ENGINEER_REVIEW"
    monkeypatch.setattr(screen_summary.datasheet, "datasheets", lambda conn, rid: [{"empty": 3}])
    s = review_summary(db, run_id)["sentences"]
    assert len(s) <= 4
    links = {p["t"]: p["href"] for x in s for p in x if p["kind"] == "link"}
    assert links["바뀐 줄 보기"] == f"/reviews/{run_id}?rev=1"
    assert links["데이터시트 채우기"] == f"/reviews/{run_id}/datasheet"
    rev = queries.run_summary(db, run_id)["revision"]
    assert any(text(x).startswith(f"개정 1을 반영해 바뀐 줄 {rev['changed']},") for x in s)
    assert any("비어 있는 작성 칸이 3개" in text(x) for x in s)


def test_processing_and_missing(db):
    """처리 중이면 한 문장, 없는 검토는 None(API 404)."""
    run_id = create_run(db, VERSION, None)
    assert [text(x) for x in review_summary(db, run_id)["sentences"]] == [
        "분석 중이라 아직 요약할 판정이 없습니다."]
    assert review_summary(db, 999999) is None


def test_home_my_turn_count(db):
    """Scenario: 내 차례 수가 홈 칸과 같음 —
    판정 확인 2건 + 실패 1건 = 3건, 마감 빠른 검토가 링크."""
    me = db.execute("INSERT INTO app_user (user_name, role) VALUES ('요약 엔지니어', 'ENGINEER') "
                    "RETURNING user_id").fetchone()[0]
    today = date.today()
    runs = []
    for stage, days, name in (("ENGINEER_REVIEW", 9, "늦은 검토"),
                              ("ENGINEER_REVIEW", 4, "급한 검토"),
                              ("FAILED", 20, "멈춘 검토"), ("APPROVED", 1, "끝난 검토")):
        rid = create_run(db, VERSION, None)
        db.execute("UPDATE review_run SET stage = %s, engineer_id = %s, due_date = %s, "
                   "project_name = %s WHERE run_id = %s",
                   (stage, me, today + timedelta(days=days), name, rid))
        runs.append(rid)
    out = home_summary(db, me)["sentences"]
    first = out[0]
    assert text(first).startswith(
        "내 차례인 검토는 3건입니다. 오늘은 급한 검토 판정 확인부터 하세요.")
    assert {"t": "급한 검토", "kind": "link", "href": f"/reviews/{runs[1]}"} in first
    due = today + timedelta(days=4)
    assert text(first).endswith(f"상신 권장일은 {day_text(due - timedelta(days=2))}, "
                                f"제출 마감은 {day_text(due)}입니다.")
    assert any(text(x) == "멈춘 검토는 분석이 멈춰 있어 다시 시도해야 합니다." for x in out)


def test_home_department_user(db, spec):
    """Scenario: 부서 사용자 — 내 차례 없음, 회신하지 않은 품질 요청 수, 협조 요청 화면 링크."""
    run_id = finished(db, spec)
    req = db.execute("SELECT min(q.requirement_id) FROM requirement q JOIN run_document rd "
                     "USING (document_id) WHERE rd.run_id = %s", (run_id,)).fetchone()[0]
    db.execute("INSERT INTO assignment (run_id, assignee_role, requirement_id, requirement_ids, "
               "status) VALUES (%s, 'QUALITY', %s, %s, 'TODO')", (run_id, req, [req]))
    n = len([a for a in review.assignments_for(db, "QUALITY") if a["status"] != "DONE"])
    assert n
    out = home_summary(db, user(db, "QUALITY"))["sentences"]
    assert text(out[0]) == "지금 내 차례인 검토는 없습니다."
    assert text(out[1]) == (f"회신하지 않은 품질 협조 요청이 {n}건입니다. "
                            "협조 요청에서 확인해 주세요.")
    assert {"t": "협조 요청", "kind": "link", "href": "/todo"} in out[1]


def test_compare_unit_not_doubled():
    """제품값 원문에 단위가 이미 있으면 다시 붙이지 않는다 ("3150 A A" 방지)."""
    from rfp_agent.pipeline.screen_summary import _compare
    j = {"req": "4,000", "req_unit": "A", "prod": "3150 A", "prod_unit": "A"}
    assert _compare(j) == "(요구 4,000 A · 제품 3150 A)"
    j = {"req": "<0.5", "req_unit": "%", "prod": "0.5 %", "prod_unit": "%"}
    assert _compare(j) == "(요구 <0.5 % · 제품 0.5 %)"
    assert _compare({"req": None, "req_unit": None, "prod": None, "prod_unit": None}) == ""
