"""시연 준비 명령 (change add-demo-setup).

명세 reference-data "시연 준비 명령"의 Scenario. 시험 DB(검토 0건)에 합성 픽스처 파일로 돌린다.
"""

import pytest

from rfp_agent.db import cli
from rfp_agent.pipeline.run import create_run

VERSION = "test-dict-v1"


@pytest.fixture
def env(db_url, monkeypatch):
    from rfp_agent.config import get_settings

    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def counts(db):
    return tuple(db.execute(q).fetchone()[0] for q in (
        "SELECT count(*) FROM answer_key", "SELECT count(*) FROM business",
        "SELECT count(*) FROM review_run"))


def test_demo_setup_on_empty_db(db, env, spec, capsys):
    """Scenario: 빈 DB에 시연 준비 — 정답지 2개, 사업 "시연 사업", 검토 1건 담당자 확인."""
    cli.main(["demo-setup", "--file", str(spec)])
    keys = dict(db.execute("SELECT key_name, made_by FROM answer_key").fetchall())
    assert keys == {"합성 RFP 28 요구사항": "CLAUDE_DRAFT", "합성 RFP 28 유형": "CLAUDE_DRAFT"}
    runs = db.execute(
        "SELECT b.business_name, r.stage FROM review_run r JOIN business b USING (business_id)"
    ).fetchall()
    assert runs == [("시연 사업", "ENGINEER_REVIEW")]
    out = capsys.readouterr().out
    assert "AI 방식" in out and "[시연 준비] 끝" in out


def test_demo_setup_refuses_db_with_runs(db, env, spec, capsys):
    """Scenario: 검토가 있는 DB — 거절하고 정답지·사업·검토 수가 그대로."""
    create_run(db, VERSION, None)
    db.commit()
    before = counts(db)
    with pytest.raises(SystemExit) as exc:
        cli.main(["demo-setup", "--file", str(spec)])
    assert "검토가 1건 있는 DB" in str(exc.value)
    assert counts(db) == before


def test_demo_setup_without_file(db, env, tmp_path):
    """Scenario: 시연 파일 없음 — 바꾸기 전에 멈추고 만드는 명령을 알림."""
    before = counts(db)
    with pytest.raises(SystemExit) as exc:
        cli.main(["demo-setup", "--file", str(tmp_path / "없음.docx")])
    assert "generate_switch_rfp.py" in str(exc.value)
    assert counts(db) == before


def test_create_database_keeps_existing(db, env, db_url, capsys):
    """--create: 이미 있는 DB는 그대로 둔다."""
    cli._create_database(db_url)
    assert "있음" in capsys.readouterr().out
