"""협조 요청 찾기·내보내기·재요청 (update-todo-search, SCR-13 v4.96).

명세 role-assignment "협조 요청 내보내기"와 "협조 요청 메일 발송"(재요청)의 Scenario.
"""

from io import BytesIO
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from rfp_agent.pipeline import queries, review
from rfp_agent.pipeline.handoff_mail import send_requests
from tests.docx_factory import build_judgment_spec
from tests.test_role_assignment import TYPE_TEST, build_task_spec, ctx, run_once, sent


@pytest.fixture
def tasks_run(db, tmp_path):
    paths = [build_judgment_spec(tmp_path / "synthetic_judgment_tasks.docx"),
             build_task_spec(tmp_path / "synthetic_feeder_tasks.docx")]
    return db, run_once(db, paths)


@pytest.fixture
def client(db, db_url, monkeypatch):
    from rfp_agent.api.main import app
    from rfp_agent.config import get_settings

    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    get_settings.cache_clear()
    yield TestClient(app)
    get_settings.cache_clear()


def _all(conn, run_id):
    return review.assignments_for(conn, None, run_id)


def _sheet(res):
    return load_workbook(BytesIO(res.content)).active


def test_export_filtered_requests(tasks_run, fake_mailer, client):
    """Scenario: 거른 요청 엑셀 — 머리 줄과 고른 요청 줄, 팀 가정 요청 줄에 "팀 가정"."""
    conn, run_id = tasks_run
    point = queries.run_proposals(conn, run_id)[0]
    conn.execute("UPDATE proposal_point SET is_assumed = TRUE WHERE point_id = %s",
                 (point["point_id"],))
    conn.commit()
    review.act(ctx(conn), run_id, "proposal_point", point["point_id"], "ADOPT")
    items = _all(conn, run_id)
    assert len(items) >= 3
    res = client.post("/api/assignments/export",
                      json={"assignment_ids": [a["assignment_id"] for a in items]})
    assert res.status_code == 200 and res.headers["x-row-count"] == str(len(items))
    assert unquote(res.headers["content-disposition"]).endswith("협조요청_전체.xlsx")
    ws = _sheet(res)
    head = [c.value for c in ws[4]]
    assert head[:9] == ["No.", "검토 번호", "검토 이름", "사업명", "수신 부서", "상태",
                        "요구사항", "원문 위치", "팀 가정"]
    body = [[c.value for c in r] for r in ws.iter_rows(min_row=5)]
    assert len(body) == len(items) and all(r[7] for r in body)         # 원문 위치 (CR-02)
    assert any(r[8] == "팀 가정" and r[4] == "영업 담당" for r in body)
    # 부서 하나만 고르면 그 부서 요청만, 파일 이름에 부서 이름
    cost = sent(conn, run_id, "COST")
    res = client.post("/api/assignments/export", json={
        "role": "COST", "assignment_ids": [a["assignment_id"] for a in items]})
    assert unquote(res.headers["content-disposition"]).endswith("협조요청_견적 담당.xlsx")
    rows = list(_sheet(res).iter_rows(min_row=5, values_only=True))
    assert len(rows) == len(cost) and {r[4] for r in rows} == {"견적 담당"}


def test_export_nothing_selected(tasks_run, client):
    """Scenario: 고른 요청이 없음 — 거절된다."""
    res = client.post("/api/assignments/export", json={"assignment_ids": []})
    assert res.status_code == 400 and "고르세요" in res.json()["detail"]
    res = client.post("/api/assignments/export", json={"assignment_ids": [10 ** 9]})
    assert res.status_code == 400


def test_all_departments_list(tasks_run, fake_mailer, client):
    """Scenario: 모든 부서 요청 목록 — 수신 부서를 정하지 않으면 세 부서 요청이 함께 온다."""
    conn, run_id = tasks_run
    point = queries.run_proposals(conn, run_id)[0]
    review.act(ctx(conn), run_id, "proposal_point", point["point_id"], "ADOPT")
    res = client.get("/api/assignments")
    assert res.status_code == 200
    roles = {a["assignee_role"] for a in res.json() if a["run_id"] == run_id}
    assert roles == {"COST", "QUALITY", "SALES"}
    assert client.get("/api/assignments", params={"role": "BOSS"}).status_code == 422


def _quality_sent(conn, run_id, fake_mailer) -> dict:
    """판정 없는 품질 요청을 보내고 하루 넘게 지난 것으로 만든다."""
    [task] = sent(conn, run_id, "QUALITY")
    assert task["text"] == TYPE_TEST
    send_requests(conn, run_id, [task["assignment_id"]], review.default_user(conn, "ENGINEER"))
    conn.execute("UPDATE assignment SET mail_sent_at = mail_sent_at - interval '25 hours' "
                 "WHERE assignment_id = %s", (task["assignment_id"],))
    conn.commit()
    assert len(fake_mailer.sent) == 1
    return sent(conn, run_id, "QUALITY")[0]


def test_resend(tasks_run, fake_mailer, client):
    """Scenario: 재요청 — 같은 주소로 다시 나가고 보낸 시각이 지금, 이력에 재요청 발송."""
    conn, run_id = tasks_run
    task = _quality_sent(conn, run_id, fake_mailer)
    url = f"/api/runs/{run_id}/assignments/send"
    # resend 없이 보내면 이미 보낸 요청은 나가지 않는다 (자동은 한 번만)
    assert client.post(url, json={"assignment_ids": [task["assignment_id"]]}).json()["sent"] == 0
    res = client.post(url, json={"assignment_ids": [task["assignment_id"]], "resend": True})
    assert res.status_code == 200 and res.json()["sent"] == 1
    assert [m["To"] for m in fake_mailer.sent] == ["quality@test", "quality@test"]
    conn.rollback()
    again = sent(conn, run_id, "QUALITY")[0]
    assert again["status"] == "DOING" and again["mail_sent_at"] > task["mail_sent_at"]
    logs = [h for h in review.history(conn, run_id, "assignment") if h["action"] == "SEND"]
    assert [bool(h["after_value"].get("resend")) for h in logs].count(True) == 1


def test_resend_engineer_only(tasks_run, fake_mailer, client):
    """Scenario: 재요청은 엔지니어만 — 견적 담당 사용자는 거절되고 보낸 시각은 그대로."""
    conn, run_id = tasks_run
    task = _quality_sent(conn, run_id, fake_mailer)
    cost_user = review.default_user(conn, "COST")
    res = client.post(f"/api/runs/{run_id}/assignments/send", json={
        "assignment_ids": [task["assignment_id"]], "resend": True, "actor_id": cost_user})
    assert res.status_code == 403
    conn.rollback()
    assert sent(conn, run_id, "QUALITY")[0]["mail_sent_at"] == task["mail_sent_at"]
    assert len(fake_mailer.sent) == 1
