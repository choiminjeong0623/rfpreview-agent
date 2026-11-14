from fastapi.testclient import TestClient

from rfp_agent.api.main import app
from rfp_agent.config import get_settings
from rfp_agent.db.migrate import migrate


def test_health_reports_degraded_when_db_is_down(monkeypatch):
    """Scenario: DB 장애."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://nobody@127.0.0.1:1/none")
    get_settings.cache_clear()
    try:
        body = TestClient(app).get("/api/health").json()
    finally:
        get_settings.cache_clear()
    assert body["status"] == "degraded"
    assert body["database"] == "down"


def test_health_reports_schema_version(monkeypatch, empty_db, db_url, settings):
    """Scenario: 정상."""
    migrate(empty_db, settings.migrations_dir)
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    try:
        body = TestClient(app).get("/api/health").json()
    finally:
        get_settings.cache_clear()
    assert body["status"] == "ok"
    latest = sorted(settings.migrations_dir.glob("*.sql"))[-1].stem
    assert body["schema_version"] == latest
