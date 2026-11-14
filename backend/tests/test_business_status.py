"""사업 현황: 사업 만들기·고치기·이력, 검토 연결, 범위 상태, 제출 완료, 내 사업, 상세,
기존 검토 묶기.

명세 business-status(add-project-status)의 Scenario.
"""

import shutil
from datetime import date, timedelta

import pytest

from rfp_agent.pipeline import business, review
from rfp_agent.pipeline.run import RunContext, create_run, execute_run

VERSION = "test-dict-v1"


def run_once(conn, paths, started_by=None):
    run_id = create_run(conn, VERSION, None, started_by)
    assert execute_run(RunContext(conn, VERSION, None, None), run_id, paths) == "ENGINEER_REVIEW"
    return run_id


def add_user(conn, name, role):
    user_id = conn.execute("INSERT INTO app_user (user_name, role) VALUES (%s, %s) "
                           "RETURNING user_id", (name, role)).fetchone()[0]
    conn.commit()
    return user_id


def set_stage(conn, run_id, stage):
    conn.execute("UPDATE review_run SET stage = %s WHERE run_id = %s", (stage, run_id))
    conn.commit()


def request_help(conn, run_id, assignee_id, role="COST", status="TODO"):
    """협조 요청 한 건 (요구사항 하나에). TODO 안 보냄, DOING 메일 보냄, DONE 회신 받음."""
    req = conn.execute("""SELECT q.requirement_id FROM requirement q JOIN run_document rd
                          USING (document_id) WHERE rd.run_id = %s LIMIT 1""",
                       (run_id,)).fetchone()[0]
    task_id = conn.execute(
        """INSERT INTO assignment (run_id, assignee_role, assignee_id, requirement_id, status,
                                   task_key)
           VALUES (%s, %s, %s, %s, %s, %s) RETURNING assignment_id""",
        (run_id, role, assignee_id, req, status, f"test-{run_id}-{assignee_id}-{role}")
    ).fetchone()[0]
    conn.commit()
    return task_id


def states(conn, business_id):
    return [r["state"] for r in business.detail(conn, business_id)["ranges"]]


@pytest.fixture
def client(db, db_url, monkeypatch):
    from fastapi.testclient import TestClient

    from rfp_agent.api.main import app
    from rfp_agent.config import get_settings

    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    get_settings.cache_clear()
    yield TestClient(app)
    get_settings.cache_clear()


DUE = "2026-12-01"


def upload(client, spec, **form):
    form.setdefault("due_date", DUE)        # 마감일은 꼭 받는다 (update-due-required)
    with spec.open("rb") as f:
        return client.post("/api/runs", data=form, files=[("files", (spec.name, f.read()))])


# ── 사업 만들기와 고치기 ──────────────────────────────────────

def test_create_business(db, client):
    """Scenario: 사업 만들기 — 목록에 PJ 번호와 함께, 만든 사람은 그 엔지니어."""
    engineer = review.default_user(db, "ENGINEER")
    made = client.post("/api/businesses", json={
        "business_name": "예시 변전소 신설", "customer_name": "예시 고객사", "country": "베트남",
        "due_date": "2026-11-20", "actor_id": engineer})
    assert made.status_code == 201
    body = made.json()
    year = date.today().year
    assert body["business_no"] == f"PJ-{year}-{body['business_id']:03d}"
    assert body["created_by"] == engineer and body["due_date"] == "2026-11-20"
    listed = client.get("/api/businesses").json()["items"]
    assert [b["business_name"] for b in listed] == ["예시 변전소 신설"]


def test_create_business_without_name(db, client):
    """Scenario: 사업명 없이 만들기 — 오류, 사업이 생기지 않는다."""
    for body in ({"customer_name": "예시 고객사"}, {"business_name": "  "}):
        refused = client.post("/api/businesses", json=body)
        assert refused.status_code == 400 and "사업명" in refused.json()["detail"]
    assert client.get("/api/businesses").json()["items"] == []


def test_sales_must_be_sales_role(db, client):
    """Scenario: 영업이 아닌 영업 담당 — 오류, 바뀌지 않는다."""
    quality = review.default_user(db, "QUALITY")
    sales = review.default_user(db, "SALES")
    made = client.post("/api/businesses", json={"business_name": "예시 사업", "sales_id": sales})
    business_id = made.json()["business_id"]
    refused = client.put(f"/api/businesses/{business_id}", json={"sales_id": quality})
    assert refused.status_code == 400 and "영업" in refused.json()["detail"]
    assert client.get(f"/api/businesses/{business_id}").json()["sales_id"] == sales
    assert client.post("/api/businesses", json={"business_name": "다른 사업",
                                                "sales_id": quality}).status_code == 400


def test_change_due_date_logs_once(db, client):
    """Scenario: 마감일 고치기 — 바뀌고 이력 1건(이전 값, 새 값)."""
    business_id = business.create(db, {"business_name": "예시 사업", "due_date": "2026-11-20"},
                                  None)
    changed = client.put(f"/api/businesses/{business_id}", json={"due_date": "2026-11-25"})
    assert changed.status_code == 200 and changed.json()["due_date"] == "2026-11-25"
    logs = client.get(f"/api/businesses/{business_id}/history").json()
    assert [(log["field"], log["before_value"], log["after_value"]) for log in logs] == [
        ("due_date", "2026-11-20", "2026-11-25")]
    client.put(f"/api/businesses/{business_id}", json={"due_date": "2026-11-25"})
    # 같은 값은 이력에 남기지 않는다
    assert len(client.get(f"/api/businesses/{business_id}/history").json()) == 1


def test_business_edit_keeps_judgments(db, spec, client):
    """Scenario: 사업을 고쳐도 판정은 그대로."""
    run_id = run_once(db, [spec])
    business_id = business.create(db, {"business_name": "예시 사업"}, None)
    business.link(db, run_id, business_id, None)
    before = client.get(f"/api/runs/{run_id}/judgments").json()
    client.put(f"/api/businesses/{business_id}", json={"customer_name": "다른 고객사",
                                                       "business_name": "고친 사업명"})
    after = client.get(f"/api/runs/{run_id}/judgments").json()
    assert [(j["judgment_id"], j["result"]) for j in after] == [
        (j["judgment_id"], j["result"]) for j in before]
    assert client.get(f"/api/runs/{run_id}").json()["project_name"] == "고친 사업명"


# ── 검토를 사업에 연결 ───────────────────────────────────────

def test_start_with_new_business(db, spec, client):
    """Scenario: 새 사업을 만들며 검토 시작 — 사업이 생기고 검토 사업명이 같다."""
    engineer = review.default_user(db, "ENGINEER")
    started = upload(client, spec, new_business_name="예시 변전소 신설",
                     customer_name="예시 고객사",
                     actor_id=str(engineer))
    assert started.status_code == 202
    summary = client.get(f"/api/runs/{started.json()['run_id']}").json()
    assert summary["business_id"] is not None and summary["business_no"].startswith("PJ-")
    assert summary["project_name"] == "예시 변전소 신설"
    detail = client.get(f"/api/businesses/{summary['business_id']}").json()
    assert detail["customer_name"] == "예시 고객사" and detail["created_by"] == engineer
    assert [r["run_id"] for r in detail["ranges"]] == [summary["run_id"]]


def test_add_to_existing_business(db, spec, client):
    """Scenario: 진행 중인 사업에 추가 — 범위 카드 두 개."""
    first = upload(client, spec, new_business_name="예시 사업").json()
    business_id = client.get(f"/api/runs/{first['run_id']}").json()["business_id"]
    second = upload(client, spec, business_id=str(business_id))
    assert second.status_code == 202
    assert len(client.get(f"/api/businesses/{business_id}").json()["ranges"]) == 2
    assert upload(client, spec, business_id=str(business_id),
                  new_business_name="또 다른 사업").status_code == 400
    assert upload(client, spec, business_id="999999").status_code == 404


def test_unlink_run(db, spec, client):
    """Scenario: 연결 해제 — 범위 카드에서 빠지고 검토 이력에 해제 1건."""
    run_id = run_once(db, [spec])
    business_id = business.create(db, {"business_name": "예시 사업"}, None)
    assert client.put(f"/api/runs/{run_id}/business",
                      json={"business_id": business_id}).json()["business_id"] == business_id
    assert client.put(f"/api/runs/{run_id}/business",
                      json={"business_id": None}).json()["business_id"] is None
    assert client.get(f"/api/businesses/{business_id}").json()["ranges"] == []
    logs = [e for e in client.get(f"/api/runs/{run_id}/history").json()
            if e["target_table"] == "review_run"]
    assert [e["reason"] for e in logs].count("사업 연결 해제") == 1


def test_linking_keeps_mismatch_scope(db, spec, client):
    """Scenario: 값 불일치 범위는 그대로 — FR-06 비교 범위(project)와 위험 조건이 같다."""
    run_a, run_b = run_once(db, [spec]), run_once(db, [spec])

    def scope():
        return (db.execute("SELECT run_id, project_id FROM review_run ORDER BY run_id").fetchall(),
                db.execute("SELECT document_id, project_id FROM document ORDER BY 1").fetchall(),
                db.execute("SELECT run_id, risk_kind, facts FROM risk_flag ORDER BY risk_id"
                           ).fetchall())

    before = scope()
    for run_id, name in ((run_a, "사업 가"), (run_b, "사업 나")):
        business.link(db, run_id, business.create(db, {"business_name": name}, None), None)
    assert scope() == before


def test_linked_project_name_is_locked(db, spec, client):
    """연결된 검토의 사업명은 검토 정보 창이 아니라 사업 상세에서 고친다 (design 위험)."""
    run_id = run_once(db, [spec])
    business.link(db, run_id, business.create(db, {"business_name": "예시 사업"}, None), None)
    refused = client.put(f"/api/runs/{run_id}/info", json={"project_name": "다른 이름"})
    assert refused.status_code == 400
    assert client.put(f"/api/runs/{run_id}/info", json={"country": "한국"}).status_code == 200


# ── 범위별 진행 상태 ─────────────────────────────────────────

def test_state_waiting_for_help(db, spec):
    """Scenario: 협조가 끝난 담당자 확인 ·
    Scenario: 협조 대기 — 메일을 보냈지만 회신 받지 않은 협조 요청이 남은 담당자 확인."""
    run_id = run_once(db, [spec])
    business_id = business.create(db, {"business_name": "예시 사업"}, None)
    business.link(db, run_id, business_id, None)
    task = request_help(db, run_id, review.default_user(db, "COST"))
    assert states(db, business_id) == ["co"]                 # 안 보냄
    db.execute("UPDATE assignment SET status = 'DOING', mail_sent_at = now() "
               "WHERE assignment_id = %s", (task,))
    db.commit()
    assert states(db, business_id) == ["co"]                 # 메일 보냄, 회신 대기
    assert business.detail(db, business_id)["ranges"][0]["open_requests"] == 1
    db.execute("UPDATE assignment SET status = 'DONE' WHERE assignment_id = %s", (task,))
    db.commit()
    assert states(db, business_id) == ["chk"]           # Scenario: 협조가 끝난 담당자 확인


def test_state_rejected(db, spec):
    """Scenario: 반려 — 결재자가 반려한 검토는 "반려"."""
    run_id = run_once(db, [spec])
    business_id = business.create(db, {"business_name": "예시 사업"}, None)
    business.link(db, run_id, business_id, None)
    set_stage(db, run_id, "REJECTED")
    assert states(db, business_id) == ["rej"]


def test_state_rules(db, spec):
    """Scenario: 상태 규칙 전부 — 분석 중, 분석 실패, 결재 대기, 제출 준비."""
    business_id = business.create(db, {"business_name": "예시 사업"}, None)
    for stage in ("PROCESSING", "FAILED", "APPROVAL", "APPROVED"):
        run_id = run_once(db, [spec])
        business.link(db, run_id, business_id, None)
        set_stage(db, run_id, stage)
    assert states(db, business_id) == ["an", "fail", "ap", "sub"]
    assert states(db, business_id) == states(db, business_id)        # 같은 데이터면 같은 상태


# ── 제출 완료 ───────────────────────────────────────────────

def two_runs(db, spec, stages):
    business_id = business.create(db, {"business_name": "예시 사업"}, None)
    for stage in stages:
        run_id = run_once(db, [spec])
        business.link(db, run_id, business_id, None)
        set_stage(db, run_id, stage)
    return business_id


def test_mark_submitted(db, spec, client):
    """Scenario: 모두 승인된 사업 제출 완료 — 사업·범위가 제출 완료, 이력 1건."""
    business_id = two_runs(db, spec, ["APPROVED", "APPROVED"])
    done = client.post(f"/api/businesses/{business_id}/submitted", json={})
    assert done.status_code == 200 and done.json()["submitted_at"] is not None
    assert [r["state"] for r in done.json()["ranges"]] == ["done", "done"]
    logs = client.get(f"/api/businesses/{business_id}/history").json()
    assert [log["field"] for log in logs] == ["submitted"]


def test_submit_refused_before_approval(db, spec, client):
    """Scenario: 승인 전 제출 완료 거절 — 오류, 상태 그대로."""
    business_id = two_runs(db, spec, ["APPROVED", "APPROVAL"])
    refused = client.post(f"/api/businesses/{business_id}/submitted", json={})
    assert refused.status_code == 409 and "승인" in refused.json()["detail"]
    assert states(db, business_id) == ["sub", "ap"]
    empty = business.create(db, {"business_name": "빈 사업"}, None)
    assert client.post(f"/api/businesses/{empty}/submitted", json={}).status_code == 409


def test_unmark_submitted(db, spec, client):
    """Scenario: 제출 완료 취소 — 제출 준비로 돌아오고 이력에 취소 1건."""
    business_id = two_runs(db, spec, ["APPROVED"])
    client.post(f"/api/businesses/{business_id}/submitted", json={})
    undone = client.delete(f"/api/businesses/{business_id}/submitted")
    assert undone.status_code == 200 and undone.json()["submitted_at"] is None
    assert [r["state"] for r in undone.json()["ranges"]] == ["sub"]
    logs = client.get(f"/api/businesses/{business_id}/history").json()
    assert [(log["field"], log["after_value"]) for log in logs][0] == ("submitted", None)
    assert len(logs) == 2


# ── 사업 목록과 내 사업 ──────────────────────────────────────

def test_my_businesses(db, spec, client):
    """Scenario: 내 사업 거르기 — 엔지니어 A의 사업만, 내 역할 엔지니어."""
    engineer_a = add_user(db, "엔지니어 A", "ENGINEER")
    other = add_user(db, "엔지니어 B", "ENGINEER")
    run_id = run_once(db, [spec])
    db.execute("UPDATE review_run SET engineer_id = %s WHERE run_id = %s", (engineer_a, run_id))
    mine = business.create(db, {"business_name": "A의 사업"}, other)
    business.link(db, run_id, mine, other)
    business.create(db, {"business_name": "관련 없는 사업"}, other)
    got = client.get("/api/businesses", params={"user_id": engineer_a, "scope": "mine"}).json()
    assert [(b["business_name"], b["my_role"]) for b in got["items"]] == [("A의 사업", "ENGINEER")]
    team = client.get("/api/businesses", params={"user_id": engineer_a, "scope": "all"}).json()
    assert len(team["items"]) == 2
    assert client.get("/api/businesses", params={"scope": "mine"}).status_code == 400


def test_helper_sees_business(db, spec, client):
    """Scenario: 협조 요청 받은 사람의 내 사업 — 내 역할 협조."""
    quality = review.default_user(db, "QUALITY")
    run_id = run_once(db, [spec])
    business_id = business.create(db, {"business_name": "예시 사업"}, None)
    business.link(db, run_id, business_id, None)
    request_help(db, run_id, quality, role="QUALITY")
    got = client.get("/api/businesses", params={"user_id": quality, "scope": "mine"}).json()
    assert [(b["business_id"], b["my_role"]) for b in got["items"]] == [(business_id, "HELPER")]


def test_summary_counts(db, spec):
    """Scenario: 요약 개수 — 진행 중 2, 3일 내 마감 1, 마감 지남 1."""
    today = db.execute("SELECT CURRENT_DATE").fetchone()[0]
    business.create(db, {"business_name": "곧 마감", "due_date": today + timedelta(days=2)}, None)
    business.create(db, {"business_name": "지남", "due_date": today - timedelta(days=1)}, None)
    done = two_runs(db, spec, ["APPROVED"])
    business.update(db, done, {"due_date": today + timedelta(days=1)}, None)
    business.set_submitted(db, done, True, None)
    got = business.business_list(db)
    assert got["summary"] == {"open": 2, "due3": 1, "overdue": 1}
    assert {b["business_name"]: b["days_left"] for b in got["items"]}["곧 마감"] == 2


def test_due_date_falls_back_to_runs(db, spec):
    """Scenario: 사업 마감이 비었을 때 — 연결 검토 중 가장 이른 마감."""
    business_id = business.create(db, {"business_name": "예시 사업"}, None)
    for due in ("2026-11-05", "2026-11-03"):
        run_id = run_once(db, [spec])
        db.execute("UPDATE review_run SET due_date = %s WHERE run_id = %s", (due, run_id))
        business.link(db, run_id, business_id, None)
    item = business.business_list(db)["items"][0]
    assert item["due_date"] == date(2026, 11, 3) and item["business_due_date"] is None


# ── 사업 상세 ───────────────────────────────────────────────

def test_people_gathered(db, spec, client):
    """Scenario: 담당자 모으기 — A, B, 견적 담당, 영업 담당이 한 번씩."""
    engineer_a = add_user(db, "엔지니어 A", "ENGINEER")
    engineer_b = add_user(db, "엔지니어 B", "ENGINEER")
    cost = review.default_user(db, "COST")
    sales = review.default_user(db, "SALES")
    business_id = business.create(db, {"business_name": "예시 사업", "sales_id": sales}, None)
    runs = []
    for engineer in (engineer_a, engineer_b):
        run_id = run_once(db, [spec])
        db.execute("UPDATE review_run SET engineer_id = %s, review_name = %s WHERE run_id = %s",
                   (engineer, f"범위 {engineer}", run_id))
        business.link(db, run_id, business_id, None)
        runs.append(run_id)
    request_help(db, runs[1], cost)
    people = client.get(f"/api/businesses/{business_id}").json()["people"]
    assert sorted((p["user_id"], p["part"]) for p in people) == sorted(
        [(engineer_a, "ENGINEER"), (engineer_b, "ENGINEER"), (cost, "HELPER"), (sales, "SALES")])
    helper = next(p for p in people if p["part"] == "HELPER")
    assert helper["run_ids"] == [runs[1]] and helper["scope"] == f"범위 {engineer_b}"


def test_documents_gathered(db, spec, tmp_path, client):
    """Scenario: 문서 모으기 — 문서 2개 검토 + 1개 검토 = 3개, 검토 번호와 함께."""
    from tests.docx_factory import build_judgment_spec

    other = build_judgment_spec(tmp_path / "synthetic_feeder.docx")
    business_id = business.create(db, {"business_name": "예시 사업"}, None)
    two = run_once(db, [spec, other])
    one = run_once(db, [spec])
    for run_id in (two, one):
        business.link(db, run_id, business_id, None)
    docs = client.get(f"/api/businesses/{business_id}").json()["documents"]
    assert [d["run_id"] for d in docs] == [two, two, one]
    assert all(d["review_no"].startswith("RV-") and d["file_name"] and d["doc_kind"] for d in docs)


def test_schedule_lists_dates(db, spec, client):
    """일정 탭: 사업 마감과 검토 시작이 날짜 순으로."""
    business_id = business.create(db, {"business_name": "예시 사업", "due_date": "2099-01-01"},
                                  None)
    run_id = run_once(db, [spec])
    business.link(db, run_id, business_id, None)
    events = client.get(f"/api/businesses/{business_id}").json()["schedule"]
    assert [e["kind"] for e in events] == ["START", "DUE"]
    assert events[0]["run_id"] == run_id and events[0]["review_no"].startswith("RV-")


# ── 기존 검토 묶기 (마이그레이션) ────────────────────────────

def test_group_existing_runs(empty_db, settings, tmp_path):
    """Scenario: 같은 사업명 묶기 — "Thai Binh" 두 검토는 사업 하나, 빈 검토는 연결 안 함."""
    from rfp_agent.db.migrate import migrate

    before = tmp_path / "migrations"
    before.mkdir()
    for path in sorted(settings.migrations_dir.glob("*.sql")):
        if path.name < "0014":
            shutil.copy(path, before / path.name)
    migrate(empty_db, before)
    user = empty_db.execute("INSERT INTO app_user (user_name, role) VALUES ('엔지니어', "
                            "'ENGINEER') RETURNING user_id").fetchone()[0]
    for name, country in (("Thai Binh", "베트남"), (" Thai Binh", "태국"), (None, None)):
        empty_db.execute(
            "INSERT INTO review_run (started_by, stage, dict_version, project_name, country) "
            "VALUES (%s, 'ENGINEER_REVIEW', 'v', %s, %s)", (user, name, country))
    empty_db.commit()
    shutil.copy(settings.migrations_dir / "0014_business.sql", before / "0014_business.sql")
    migrate(empty_db, before)
    rows = empty_db.execute("SELECT business_name, country FROM business").fetchall()
    assert rows == [("Thai Binh", "베트남")]                  # 먼저 시작한 검토의 국가
    linked = empty_db.execute("SELECT business_id IS NOT NULL FROM review_run ORDER BY run_id"
                              ).fetchall()
    assert [r[0] for r in linked] == [True, True, False]


def test_demo_businesses_command(db, spec, client, capsys):
    """시연용 사업 명령: 사업 하나에 파일마다 검토 하나, 담당은 기본 엔지니어 (design 8)."""
    from rfp_agent.db.cli import main

    main(["demo-businesses", "--business", "시연 사업", str(spec), "--customer", "Demo Grid Co.",
          "--due-in", "7"])
    item = client.get("/api/businesses").json()["items"][0]
    assert (item["business_name"], item["customer_name"], item["days_left"]) == (
        "시연 사업", "Demo Grid Co.", 7)
    assert [r["engineer_name"] for r in item["ranges"]] == ["기본 엔지니어"]
    assert "시연 사업" in capsys.readouterr().out
