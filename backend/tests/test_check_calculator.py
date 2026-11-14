"""검산 확인 (add-check-calculator). 명세 engineering-check "검산 계산 확인"의 Scenario.

분석 검산과 같은 규칙(배수·반올림·R10)을 쓰는지 본다. 저장하지 않으므로 DB를 보지 않는다.
"""

import pytest

from rfp_agent.pipeline.engineering import peak_check


def test_peak_check_violation_and_pass():
    """Scenario: 검산 계산 확인 — 50 kA·50 Hz·100 kA는 위반(계산값 125), 125 kA는 통과."""
    out = peak_check(50, 50, 100)
    assert (out["factor"], out["expected_ka"], out["result"]) == (2.5, 125.0, "VIOLATION")
    assert peak_check(50, 50, 125)["result"] == "PASS"


def test_peak_check_same_rules_as_analysis():
    """분석 검산과 같은 허용: 60 Hz 31.5 × 2.6 = 81.9 → 82, 50 Hz 25 × 2.5 = 62.5 → R10 63."""
    assert peak_check(31.5, 60, 82)["result"] == "PASS"
    out = peak_check(25, 50, 63)
    assert out["result"] == "PASS" and 63 in out["allowed_ka"]
    # 60 Hz에 50 Hz 표준값을 옮겨 적은 것
    assert peak_check(40, 60, 100)["result"] == "VIOLATION"


def test_peak_check_no_factor():
    """Scenario: 배수 없는 주파수 — 55 Hz면 확인 필요, 계산값 없음."""
    out = peak_check(40, 55, 100)
    assert (out["result"], out["expected_ka"], out["reason_code"]) == (
        "NEEDS_REVIEW", None, "NO_FACTOR")


@pytest.fixture
def client(db, db_url, monkeypatch):
    from fastapi.testclient import TestClient

    from rfp_agent.api.main import app
    from rfp_agent.config import get_settings

    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    yield TestClient(app)
    get_settings.cache_clear()


def test_peak_check_api(client):
    """API는 같은 함수의 답을 돌려주고, 0 이하 값은 받지 않는다."""
    url = "/api/engineering/peak-check"
    res = client.get(url, params={"ik_ka": 50, "frequency_hz": 50, "peak_ka": 100})
    assert res.status_code == 200
    body = res.json()
    assert (body["factor"], body["expected_ka"], body["result"]) == (2.5, 125.0, "VIOLATION")
    bad = client.get(url, params={"ik_ka": 0, "frequency_hz": 50, "peak_ka": 100})
    assert bad.status_code == 422
