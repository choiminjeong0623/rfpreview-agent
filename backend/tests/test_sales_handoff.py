"""영업 인계 (add-submission-package, FR-11 확장). 명세 role-assignment의 Scenario."""

import zipfile
from io import BytesIO

import pytest

from rfp_agent.config import get_settings
from rfp_agent.pipeline import datasheet, queries, review, sales_handoff
from rfp_agent.pipeline.run import RunContext, create_run, execute_run

VERSION = "test-dict-v1"


def ctx(conn):
    return RunContext(conn, VERSION, None, None)


@pytest.fixture
def run(db, spec):
    run_id = create_run(db, VERSION, None)
    assert execute_run(ctx(db), run_id, [spec]) == "ENGINEER_REVIEW"
    return run_id


def engineer(conn):
    return review.default_user(conn, "ENGINEER")


def first_sheet(conn, run_id):
    return datasheet.datasheets(conn, run_id)[0]["table_id"]


def confirm_all(conn, run_id, table_id, leave=0):
    """데이터시트 후보 칸을 화면처럼 하나씩 확정한다. leave칸은 후보로 남긴다."""
    rows = [r for r in datasheet.datasheet(conn, run_id, table_id)["rows"] if r["state"] == "cand"]
    for r in rows[leave:]:
        if r["target"] == "warranty":
            review.act(ctx(conn), run_id, "warranty_candidate", r["candidate_id"], "CONFIRM")
        else:
            review.act(ctx(conn), run_id, "judgment", r["judgment_id"], "CONFIRM")
    return datasheet.datasheet(conn, run_id, table_id)["counts"]


def approve(conn, run_id):
    review.finish_review(conn, run_id, review.default_user(conn, "APPROVER"), "인계 시험",
                         engineer(conn))
    review.decide(conn, run_id, "APPROVED", "승인", review.default_user(conn, "APPROVER"))


def test_send_confirmed_datasheet(db, run, fake_mailer):
    """Scenario: 확정한 데이터시트 넘기기 — 메일 1통, 엑셀 1개, 기록 1건, SEND 이력."""
    table = first_sheet(db, run)
    counts = confirm_all(db, run, table)
    assert counts["cand"] == 0
    out = sales_handoff.send_datasheet(db, run, table, engineer(db))
    assert out["sent"] and out["mail_to"] == "sales@test" and out["empty"] == counts["empty"]
    [mail] = fake_mailer.sent
    assert mail["To"] == "sales@test" and mail["Subject"].startswith("[데이터시트]")
    [att] = list(mail.iter_attachments())
    assert att.get_filename() == out["files"][0] and att.get_filename().endswith(".xlsx")
    assert f"확인 필요 {counts['empty']}칸" in mail.get_body().get_content()
    [h] = sales_handoff.handoffs(db, run)
    assert (h["kind"], h["table_id"], h["mail_error"]) == ("DATASHEET", table, None)
    [log] = [x for x in review.history(db, run) if x["target_table"] == "sales_handoff"]
    assert log["action"] == "SEND" and log["target_id"] == h["handoff_id"]


def test_candidates_left_refused(db, run, fake_mailer):
    """Scenario: 후보 칸이 남은 데이터시트 — 보내지 않고 "후보 2칸을 먼저 확정"."""
    table = first_sheet(db, run)
    assert confirm_all(db, run, table, leave=2)["cand"] == 2
    with pytest.raises(sales_handoff.HandoffRefused, match="후보 2칸을 먼저 확정해 주세요"):
        sales_handoff.send_datasheet(db, run, table, engineer(db))
    assert fake_mailer.sent == [] and sales_handoff.handoffs(db, run) == []


def test_no_sales_address(db, run, fake_mailer):
    """Scenario: 영업 주소 없음 — 메일 없음, 기록에 "주소 없음"."""
    fake_mailer.addresses.pop("SALES")
    table = first_sheet(db, run)
    confirm_all(db, run, table)
    out = sales_handoff.send_datasheet(db, run, table, engineer(db))
    assert not out["sent"] and out["error"] == "주소 없음" and fake_mailer.sent == []
    [h] = sales_handoff.handoffs(db, run)
    assert h["mail_error"] == "주소 없음" and h["mail_to"] is None


def test_send_failure_recorded(db, run, fake_mailer):
    """발송 실패 — 정해진 횟수(4번) 시도 뒤 기록에 실패 (CR-12)."""
    fake_mailer.fail_times = 10
    table = first_sheet(db, run)
    confirm_all(db, run, table)
    out = sales_handoff.send_datasheet(db, run, table, engineer(db))
    assert not out["sent"] and "보내지 못했습니다" in out["error"] and fake_mailer.tries == 4


def test_resend_adds_record(db, run, fake_mailer):
    """Scenario: 다시 넘기기 — 메일 한 통 더, 기록 2건."""
    table = first_sheet(db, run)
    confirm_all(db, run, table)
    sales_handoff.send_datasheet(db, run, table, engineer(db))
    sales_handoff.send_datasheet(db, run, table, engineer(db))
    assert len(fake_mailer.sent) == 2 and len(sales_handoff.handoffs(db, run)) == 2


def test_package_before_approval_refused(db, run):
    """Scenario: 승인 전 패키지 — "결재 승인 뒤에 만들 수 있습니다"."""
    with pytest.raises(sales_handoff.HandoffRefused, match="결재 승인 뒤에 만들 수 있습니다"):
        sales_handoff.build_package(db, run)


def test_package_contents(db, run):
    """Scenario: 패키지 내려받기 — 일탈 Word, TBE, 데이터시트, 목록. 질의 없으면 빼고 이유."""
    j = next(j for j in queries.run_judgments(db, run, limit=500) if j["result"] == "COMPLY")
    review.act(ctx(db), run, "judgment", j["judgment_id"], "EDIT",
               {"result": "DEVIATION_CANDIDATE"}, "시험용 일탈")
    for q in queries.run_outputs(db, run, "QUERY"):
        db.execute("UPDATE output_item SET status = 'REMOVED' WHERE item_id = %s", (q["item_id"],))
    db.commit()
    approve(db, run)
    name, body, names = sales_handoff.build_package(db, run)
    review_no = queries.run_summary(db, run)["review_no"]
    assert name == f"인계패키지_{review_no}.zip"
    z = zipfile.ZipFile(BytesIO(body))
    inside = z.namelist()
    assert inside == names
    assert any(n.startswith("일탈") and n.endswith(".docx") for n in inside)
    assert not any(n.startswith("질의") for n in inside)
    assert any(n.startswith("TBE_") for n in inside)
    sheets = datasheet.datasheets(db, run)
    assert sum(n.startswith("Datasheet_") for n in inside) == len(sheets) > 0
    readme = z.read("목록.txt").decode("utf-8")
    assert "질의 후보 없음" in readme and review_no in readme
    assert sales_handoff.build_package(db, run)[2] == names              # 같은 입력 같은 결과


def test_send_package(db, run, fake_mailer):
    """Scenario: 패키지 영업에 보내기 — zip 1개 메일 1통, 기록 1건."""
    approve(db, run)
    out = sales_handoff.send_package(db, run, engineer(db))
    assert out["sent"]
    [mail] = fake_mailer.sent
    assert mail["Subject"].startswith("[영업 인계]")
    [att] = list(mail.iter_attachments())
    assert att.get_filename().endswith(".zip") and att.get_content_type() == "application/zip"
    [h] = sales_handoff.handoffs(db, run)
    assert h["kind"] == "PACKAGE" and "목록.txt" in h["file_names"]


def test_handoff_api(db, db_url, run, fake_mailer, monkeypatch):
    """Scenario: 엔지니어만 넘김 ·
    Scenario: 엔지니어만 넘김 + API — 승인자는 403, 승인 전 패키지 409, 엔지니어는 200."""
    from fastapi.testclient import TestClient

    from rfp_agent.api.main import app

    table = first_sheet(db, run)
    confirm_all(db, run, table)
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    get_settings.cache_clear()
    try:
        c = TestClient(app)
        boss = review.default_user(db, "APPROVER")
        res = c.post(f"/api/runs/{run}/datasheet/handoff", json={"table_id": table,
                                                                 "actor_id": boss})
        assert res.status_code == 403 and fake_mailer.sent == []
        assert c.get(f"/api/runs/{run}/package").status_code == 409
        res = c.post(f"/api/runs/{run}/datasheet/handoff",
                     json={"table_id": table, "actor_id": engineer(db)})
        assert res.status_code == 200 and res.json()["sent"]
        [h] = c.get(f"/api/runs/{run}/handoffs").json()
        assert h["kind"] == "DATASHEET" and h["sent_by_name"] == "기본 엔지니어"
        approve(db, run)
        res = c.get(f"/api/runs/{run}/package")
        assert res.status_code == 200 and res.headers["content-type"] == "application/zip"
    finally:
        get_settings.cache_clear()
