"""FR-11 유형별 담당자 전달. 명세 role-assignment의 Scenario."""

import pytest
from docx import Document

from rfp_agent.pipeline import queries, review
from rfp_agent.pipeline.handoff_mail import send_requests
from rfp_agent.pipeline.run import RunContext, create_run, execute_run
from tests.docx_factory import build_judgment_spec

VERSION = "test-dict-v1"
LOSS_CLAUSE = ("The guaranteed losses shall be capitalized at the rates below and added to "
               "give a total evaluated price.")
TYPE_TEST = "Type Test reports of the offered equipment shall be submitted with the bid."
EXPERIENCE = "The manufacturer shall have at least ten years experience in the offered equipment."


def build_task_spec(path):
    """견적(손실 환산 조항)·품질(형식시험)·영업(제조사 실적, 장비 세 곳에 반복) 문장이 있는 문서."""
    doc = Document()
    doc.add_paragraph("EMPLOYER'S REQUIREMENTS")
    doc.add_paragraph("1. GENERAL")
    doc.add_paragraph(LOSS_CLAUSE)
    doc.add_paragraph(TYPE_TEST)
    for no, equipment in enumerate(("GIS", "POWER TRANSFORMER", "SWITCHGEAR"), start=2):
        doc.add_paragraph(f"{no}. {equipment}")
        doc.add_paragraph(f"The {equipment.lower()} shall be as specified in the data sheet.")
        doc.add_paragraph(f"a) {EXPERIENCE}")
    doc.add_paragraph("5. PAINTING")
    doc.add_paragraph("The painting shall be as specified in the general specification.")
    doc.save(str(path))
    return path


def run_once(conn, paths):
    run_id = create_run(conn, VERSION, None)
    assert execute_run(RunContext(conn, VERSION, None, None), run_id, paths) == "ENGINEER_REVIEW"
    return run_id


def ctx(conn):
    return RunContext(conn, VERSION, None, None)


@pytest.fixture
def tasks_run(db, tmp_path):
    paths = [build_judgment_spec(tmp_path / "synthetic_judgment_tasks.docx"),
             build_task_spec(tmp_path / "synthetic_feeder_tasks.docx")]
    return db, run_once(db, paths)


def sent(conn, run_id, role):
    return review.assignments_for(conn, role, run_id)


def test_cost_clause_goes_to_cost(tasks_run):
    """Scenario: 비용 영향 유형 줄 ·
    Scenario: 비용 영향 유형 — 손실 환산 조항은 견적 담당 "내 할 일"에 원문 위치와 함께 1건."""
    conn, run_id = tasks_run
    [task] = sent(conn, run_id, "COST")
    assert task["type_code"] == "COST" and task["text"] == LOSS_CLAUSE
    assert task["status"] == "TODO" and task["repeat_count"] == 1
    assert [(loc["file_no"], loc["line_start"]) for loc in task["locations"]] == [(92, 3)]
    cost_user = review.default_user(conn, "COST")
    assert review.my_tasks(conn, cost_user)["assignments"][0]["assignment_id"] == \
        task["assignment_id"]


def test_test_clause_goes_to_quality(tasks_run):
    """Scenario: 시험 유형 줄 · Scenario: 시험 유형 — 형식시험 조항은 품질 담당에게 간다."""
    conn, run_id = tasks_run
    assert [t["text"] for t in sent(conn, run_id, "QUALITY")] == [TYPE_TEST]


def test_repeated_condition_is_one_task(tasks_run):
    """Scenario: 장비마다 반복되는 제조사 자격 ·
    Scenario: 반복 조건 — 장비 세 곳에 같은 제조사 실적 조건이 있으면 영업에 1건, 반복 3."""
    conn, run_id = tasks_run
    [task] = [t for t in sent(conn, run_id, "SALES") if t["point_id"] is None]
    assert task["type_code"] == "MAKER_QUAL" and task["repeat_count"] == 3
    assert len(task["requirement_ids"]) == 3 and len(task["locations"]) == 3


def test_engineer_types_are_not_sent(tasks_run):
    """Scenario: 기술 성능 줄 ·
    Scenario: 엔지니어 몫 — 기술 성능·위험 조건 요구사항은 담당자에게 보내지 않는다."""
    conn, run_id = tasks_run
    types = {t["type_code"] for role in ("COST", "QUALITY", "SALES")
             for t in sent(conn, run_id, role) if t["type_code"]}
    assert types == {"COST", "TEST", "MAKER_QUAL"}
    assert sent(conn, run_id, "ENGINEER") == []


def test_adopted_point_goes_to_sales(tasks_run):
    """Scenario: 채택된 제안 포인트 1건 — 영업 전달 기록 1건, 버린 포인트는 보내지 않는다."""
    conn, run_id = tasks_run
    points = queries.run_proposals(conn, run_id)
    assert len(points) >= 2
    first, second = points[:2]
    assert [t for t in sent(conn, run_id, "SALES") if t["point_id"]] == []   # 채택 전
    review.act(ctx(conn), run_id, "proposal_point", first["point_id"], "ADOPT")
    review.act(ctx(conn), run_id, "proposal_point", second["point_id"], "DISCARD",
               reason="고객이 중요하게 보지 않는 항목")
    [task] = [t for t in sent(conn, run_id, "SALES") if t["point_id"]]
    assert task["point_id"] == first["point_id"] and task["point_kind"] == first["point_kind"]
    assert task["locations"]


def test_status_kept_after_rebuild(tasks_run, fake_mailer):
    """Scenario: 다시 만들어도 진행 상태 유지 — 메일 보냄인 영업 할 일은 판정 확정 뒤에도 그대로."""
    conn, run_id = tasks_run
    point = queries.run_proposals(conn, run_id)[0]
    review.act(ctx(conn), run_id, "proposal_point", point["point_id"], "ADOPT")
    [before] = [t for t in sent(conn, run_id, "SALES") if t["point_id"]]
    assert before["status"] == "DOING" and before["mail_sent_at"] is not None
    judgment = next(j for j in queries.run_judgments(conn, run_id, limit=500)
                    if j["result"] == "COMPLY")
    review.act(ctx(conn), run_id, "judgment", judgment["judgment_id"], "CONFIRM")
    [after] = [t for t in sent(conn, run_id, "SALES") if t["point_id"]]
    assert after["status"] == "DOING" and after["mail_sent_at"] == before["mail_sent_at"]
    assert after["sent_by_name"] == before["sent_by_name"] == "기본 엔지니어"
    assert after["mail_to"] == "sales@test"
    assert len(fake_mailer.sent) == 1                   # 다시 보내지 않았다


def test_engineer_records_reply(tasks_run):
    """Scenario: 엔지니어가 회신 받음 기록 — 회신 요지, 기록한 사람, 시각이 남고 되돌릴 수 있다."""
    conn, run_id = tasks_run
    [task] = sent(conn, run_id, "QUALITY")
    engineer = review.default_user(conn, "ENGINEER")
    with pytest.raises(review.ReviewError) as err:      # 아직 안 보낸 요청
        review.set_assignment_status(conn, task["assignment_id"], "DONE", engineer)
    assert err.value.status == 409
    send_requests(conn, run_id, [task["assignment_id"]], engineer)
    review.set_assignment_status(conn, task["assignment_id"], "DONE", engineer,
                                 "성적서 3종 11-05까지 보냄")
    [done] = sent(conn, run_id, "QUALITY")
    assert done["status"] == "DONE" and done["reply_note"] == "성적서 3종 11-05까지 보냄"
    assert done["replied_by_name"] == "기본 엔지니어" and done["replied_at"] is not None
    actions = [h["action"] for h in review.history(conn, run_id, "assignment")]
    assert actions == ["SEND", "REPLY"]
    review.set_assignment_status(conn, task["assignment_id"], "DOING", engineer)
    [back] = sent(conn, run_id, "QUALITY")
    assert back["status"] == "DOING" and back["reply_note"] is None


def test_only_engineer_changes_status(tasks_run):
    """Scenario: 다른 역할 사용자 — 견적 담당은 자기 할 일 상태를 바꿀 수 없다."""
    conn, run_id = tasks_run
    [task] = sent(conn, run_id, "COST")
    cost = review.default_user(conn, "COST")
    engineer = review.default_user(conn, "ENGINEER")
    send_requests(conn, run_id, [task["assignment_id"]], engineer)
    for status, user, code in (("DONE", cost, 403), ("LATER", engineer, 400)):
        with pytest.raises(review.ReviewError) as err:
            review.set_assignment_status(conn, task["assignment_id"], status, user)
        assert err.value.status == code
    with pytest.raises(review.ReviewError) as err:
        review.set_assignment_status(conn, 999999, "DONE", engineer)
    assert err.value.status == 404
    assert review.set_assignment_status(conn, task["assignment_id"], "DONE", engineer)["status"] \
        == "DONE"


def test_review_cards_for_engineer_and_approver(tasks_run):
    """Scenario: 엔지니어·승인자의 내 할 일 — 멈춰 있는 검토와 걸린 승인 기준을 보여 준다."""
    conn, run_id = tasks_run
    engineer = review.default_user(conn, "ENGINEER")
    approver = review.default_user(conn, "APPROVER")
    mine = review.my_tasks(conn, engineer)
    [card] = [c for c in mine["reviews"] if c["run_id"] == run_id]
    assert mine["role"] == "ENGINEER" and mine["assignments"] == []
    assert card["summary"]["stage"] == "ENGINEER_REVIEW" and card["criteria"]
    assert [c for c in review.my_tasks(conn, approver)["reviews"] if c["run_id"] == run_id] == []
    review.finish_review(conn, run_id, approver, "결재 바랍니다")
    [card] = [c for c in review.my_tasks(conn, approver)["reviews"] if c["run_id"] == run_id]
    assert "AR-01" in [r["ar_code"] for r in card["criteria"]]


def test_tasks_api(tasks_run, db_url, monkeypatch):
    """내 할 일 API와 할 일 상태 바꾸기 API."""
    from fastapi.testclient import TestClient

    from rfp_agent.api.main import app
    from rfp_agent.config import get_settings

    conn, run_id = tasks_run
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    get_settings.cache_clear()
    try:
        client = TestClient(app)
        quality = review.default_user(conn, "QUALITY")
        mine = client.get("/api/tasks", params={"user_id": quality}).json()
        [task] = [t for t in mine["assignments"] if t["run_id"] == run_id]
        assert mine["role"] == "QUALITY" and task["text"] == TYPE_TEST
        url = f"/api/assignments/{task['assignment_id']}"
        engineer = review.default_user(conn, "ENGINEER")
        result = client.post(f"/api/runs/{run_id}/assignments/send",
                             json={"assignment_ids": [task["assignment_id"]],
                                   "actor_id": engineer}).json()
        assert result == {"sent": 1, "failed": 0, "no_address": 0, "mails": 1}
        assert client.put(url, json={"status": "DONE", "actor_id": quality}).status_code == 403
        assert client.put(url, json={"status": "LATER", "actor_id": engineer}).status_code == 422
        assert client.put(url, json={"status": "DONE", "actor_id": engineer,
                                     "reply_note": "회신 받음"}).status_code == 200
        listed = client.get(f"/api/runs/{run_id}/assignments", params={"role": "QUALITY"}).json()
        assert [(t["status"], t["reply_note"]) for t in listed] == [("DONE", "회신 받음")]
        refused = client.post(f"/api/runs/{run_id}/assignments/send",
                              json={"assignment_ids": [], "actor_id": quality})
        assert refused.status_code == 403
        assert client.get("/api/tasks", params={"user_id": 999999}).status_code == 400
    finally:
        get_settings.cache_clear()


def test_department_requests_api(tasks_run, db_url, monkeypatch):
    """Scenario: 수신 부서별 요청 현황 — 부서에 보낸 요청을 검토 번호·파일 이름과 모은다."""
    from fastapi.testclient import TestClient

    from rfp_agent.api.main import app
    from rfp_agent.config import get_settings

    conn, run_id = tasks_run
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    get_settings.cache_clear()
    try:
        client = TestClient(app)
        listed = client.get("/api/assignments", params={"role": "QUALITY"}).json()
        [task] = [t for t in listed if t["run_id"] == run_id]
        assert task["text"] == TYPE_TEST and task["status"] == "TODO"
        assert task["review_no"].endswith(f"-{run_id:03d}")
        assert task["file_name"] == "synthetic_feeder_tasks.docx"
        assert task["engineer_name"] is None or isinstance(task["engineer_name"], str)
        assert client.get("/api/assignments", params={"role": "ENGINEER"}).status_code == 422
    finally:
        get_settings.cache_clear()
