"""합성 묶음 A 문서로 판정 → 보증값 → 손실 환산 → 일탈·질의 목록 → 제안 포인트를 DB까지 돌린다.

명세 compliance-judgment, warranty-candidates, bid-outputs, proposal-points, evidence-integrity의
Scenario. 실제 문서로 하는 확인은 test_corpus.py에 있다.
"""


from rfp_agent.pipeline import queries
from rfp_agent.pipeline.run import RunContext, create_run, execute_run, switch_product
from tests.conftest import FakeLLM
from tests.docx_factory import build_feeder_copy, build_gis_spec

VERSION = "test-dict-v1"
def run_once(conn, paths, llm=None):
    run_id = create_run(conn, VERSION, llm)
    assert execute_run(RunContext(conn, VERSION, llm, None), run_id, paths) == "ENGINEER_REVIEW"
    return run_id


def judgment(conn, run_id, table, name):
    rows = [j for j in queries.run_judgments(conn, run_id, limit=500)
            if j["item_name_raw"] == name and j["equipment_group"].startswith("T")
            and j["locations"][0]["table_name"] == table]
    assert len(rows) == 1, (table, name, rows)
    return rows[0]


def test_product_exceeding_requirement_is_deviation(db, spec):
    """Scenario: 요구를 넘는 제품 — 4,000 A를 GIS-245-50(3,150 A)와 비교하면 일탈 후보."""
    run_id = run_once(db, [spec])
    j = judgment(db, run_id, "TS-230-GIS", "Rated normal current of main busbar")
    assert (j["product_code"], j["result"], j["reason_code"]) == (
        "GIS-245-50", "DEVIATION_CANDIDATE", "NOT_MET")
    assert j["product_selected_by"] == "AUTO" and j["margin_value"] is None


def test_bundle_c_is_not_judged(seeded_db, tmp_path):
    """Scenario: 묶음 C 문서 — 판정을 만들지 않는다."""
    run_id = run_once(seeded_db, [build_gis_spec(tmp_path / "synthetic_154kV_GIS_spec.docx")])
    assert queries.run_summary(seeded_db, run_id)["judgments"] == 0


def test_no_product_value_and_unit_difference(db, spec):
    """Scenario: 제품값 없음 / 단위가 다름 — 확인 필요이고 여유는 계산하지 않는다."""
    run_id = run_once(db, [spec])
    gas = judgment(db, run_id, "TS-115-GIS", "Annual leakage rate for each gas compartment")
    assert (gas["product_code"], gas["result"], gas["reason_code"]) == (
        "GIS-145", "NEEDS_REVIEW", "NO_PRODUCT_VALUE")
    unit = judgment(db, run_id, "TS-115-GIS", "Rated normal current of bus coupler")
    assert (unit["result"], unit["reason_code"]) == ("NEEDS_REVIEW", "UNIT_DIFF")
    assert gas["margin_value"] is None and unit["margin_value"] is None
    assert gas["margin_direction"] == unit["margin_direction"] == "NOT_CALC"


def test_time_condition_margin(db, spec):
    """Scenario: 40 kA 1초 요구, 3초 제품 — 준수, GIS-145, 시간 3배, 강점."""
    run_id = run_once(db, [spec])
    j = judgment(db, run_id, "TS-115-GIS", "Rated short-time withstand current, (1 sec.)")
    assert (j["result"], j["product_code"], j["margin_kind"], float(j["margin_value"]),
            j["margin_direction"]) == ("COMPLY", "GIS-145", "TIME_RATIO", 3, "STRENGTH")


def test_switching_product_rejudges(db, spec):
    """Scenario: 비교 제품에 따라 바뀌는 판정 — GIS-145 준수 2건 → GIS-145-P7 일탈 2건."""
    run_id = run_once(db, [spec])
    names = ["Rated normal current", "Rated frequency"]
    before = [judgment(db, run_id, "TS-115-GIS", n) for n in names]
    assert [(j["product_code"], j["result"]) for j in before] == [("GIS-145", "COMPLY")] * 2
    group = before[0]["equipment_group"]
    switch_product(RunContext(db, VERSION, None, None), run_id, group, "GIS-145-P7")
    after = [judgment(db, run_id, "TS-115-GIS", n) for n in names]
    assert [(j["product_code"], j["result"], j["product_selected_by"]) for j in after] == [
        ("GIS-145-P7", "DEVIATION_CANDIDATE", "ENGINEER")] * 2
    old = db.execute("SELECT is_current FROM judgment WHERE judgment_id = ANY(%s)",
                     ([j["judgment_id"] for j in before],)).fetchall()
    assert old == [(False,), (False,)]
    other = judgment(db, run_id, "TS-230-GIS", "Rated voltage")
    assert other["product_code"] == "GIS-245-50"        # 다른 묶음은 그대로


def test_warranty_candidates(db, spec):
    """Scenario: 회사 고정값 / 제품표에 없는 값."""
    run_id = run_once(db, [spec])
    rows = {r["item_name_raw"]: r for r in queries.run_warranty(db, run_id, limit=500)}
    maker = rows["Manufacturer's name"]
    assert (maker["candidate_value"], maker["source_kind"], maker["status"]) == (
        "LS ELECTRIC", "FIXED", "CANDIDATE")
    weight = rows["Weight of circuit breaker"]
    assert (weight["candidate_value"], weight["status"], weight["reason_code"]) == (
        None, "EMPTY_REVIEW", "NO_PRODUCT_VALUE")


def test_repeated_deviation_is_one_item(db, spec):
    """Scenario: 세 곳에 반복된 일탈 — 일탈 목록 1건, 원문 위치 3곳."""
    run_id = run_once(db, [spec])
    items = [i for i in queries.run_outputs(db, run_id, "DEVIATION") if "4,000" in i["text_draft"]]
    assert len(items) == 1
    assert len(items[0]["sources"]) == 3 and len(items[0]["locations"]) == 3
    assert items[0]["number_check"] == "OK" and items[0]["list_name"]


def test_same_query_in_two_documents(db, spec, tmp_path):
    """Scenario: 두 문서에 같은 질의 — 질의 1건, 위치 2곳."""
    copy = build_feeder_copy(tmp_path / "synthetic_feeder.docx")
    run_id = run_once(db, [spec, copy])
    items = [i for i in queries.run_outputs(db, run_id, "QUERY") if "2,000" in i["text_draft"]
             or "2000" in i["text_draft"]]
    assert len(items) == 1, [i["text_draft"] for i in items]
    assert sorted(loc["file_no"] for loc in items[0]["locations"]) == [91, 92]


def test_gas_leakage_query_and_deviation_are_linked(db, tmp_path):
    """Scenario: 154 kV 가스 누설 — 0.5 % 일탈 후보와 0.5 % / 1 % 질의 후보가 서로 연결된다."""
    doc = build_gis_spec(tmp_path / "synthetic_154kV_bundle_a.docx")
    run_id = run_once(db, [doc])
    outputs = queries.run_outputs(db, run_id)
    deviation = next(i for i in outputs if i["list_kind"] == "DEVIATION"
                     and "0.5" in i["text_draft"])
    query = next(i for i in outputs if i["list_kind"] == "QUERY" and "0.5" in i["text_draft"]
                 and "1 %" in i["text_draft"])
    assert deviation["linked_items"] == [query["item_id"]]
    assert query["linked_items"] == [deviation["item_id"]]
    # 요구 "<0.5"의 비교 기호가 남아야 제품 0.5 %와 같은 값으로 읽히지 않는다
    assert "<0.5" in deviation["text_draft"] and deviation["number_check"] == "OK"


def test_number_mismatch_is_flagged(db, spec):
    """Scenario: 근거와 다른 숫자 (목록·제안 포인트) — 숫자 불일치로 표시된다."""
    run_id = run_once(db, [spec], FakeLLM(text="초안 {all} 값은 9999입니다."))
    outputs = queries.run_outputs(db, run_id)
    points = queries.run_proposals(db, run_id)
    assert outputs and points
    for row in outputs + points:
        assert row["drafted_by"] == "AI"
        assert row["number_check"] == "MISMATCH" and "9999" in row["number_detail"]


def test_missing_deviation_sends_to_ar07(db, spec):
    """Scenario: 일탈 하나가 빠짐 — 누락이 표시되고 승인 기준 AR-07에 해당한다."""
    run_id = run_once(db, [spec])
    check = queries.submission_check(db, run_id)
    assert check["ar_codes"] == [] and check["missing_judgment_ids"] == []
    feeder = next(i for i in queries.run_outputs(db, run_id, "DEVIATION")
                      if "3,500" in i["text_draft"])
    db.execute("UPDATE output_item SET status = 'REMOVED' WHERE item_id = %s",
               (feeder["item_id"],))
    from rfp_agent.pipeline.outputs import check_submission
    check = check_submission(db, run_id)
    assert check["deviation_candidates"] == check["deviation_listed"] + 1
    assert len(check["missing_judgment_ids"]) == 1 and check["ar_codes"] == ["AR-07"]


def test_proposal_points(db, spec):
    """Scenario: 시간 여유 / 확인 필요 판정 — 준수+강점만 후보, 확인 필요는 후보가 아니다."""
    run_id = run_once(db, [spec])
    points = queries.run_proposals(db, run_id)
    time_points = [p for p in points if "3배" in p["text_draft"] and p["product_code"] == "GIS-145"]
    assert time_points and all(p["status"] == "CANDIDATE" and p["locations"] for p in points)
    assert "GIS-145" in time_points[0]["basis"] and "1초" in time_points[0]["basis"]
    judged = {p["judgment_id"] for p in points if p["judgment_id"]}
    review = {r[0] for r in db.execute(
        "SELECT judgment_id FROM judgment WHERE run_id = %s AND result <> 'COMPLY'", (run_id,))}
    assert not judged & review


def _mapping(conn):
    return ({k: (col, fixed, usage) for k, col, fixed, usage in conn.execute(
        "SELECT item_key, pm_column, fixed_key, usage FROM item_pm_mapping")},
        dict(conn.execute("SELECT fixed_key, fixed_value FROM company_fixed_value")))


def test_warranty_from_product_table(db):
    """Scenario: 제품표 값 — TS-SG 차단기 무게, 비교 제품 VCB-SUSOL-24-40-3150이면 318 kg."""
    from rfp_agent.pipeline.products import load_products
    from rfp_agent.pipeline.warranty import _candidate

    products = {p.code: p for p in load_products(db)}
    mapping, fixed = _mapping(db)
    row = _candidate(1, 1, "weight", "kg", products["VCB-SUSOL-24-40-3150"], mapping, fixed)
    # (run, judgment, 값, 단위, 출처, 제품, 칸, 고정값 키, 상태, 사유, 팀 가정)
    assert row[2:10] == ("318", "kg", "PM", "VCB-SUSOL-24-40-3150", "weight_kg", None,
                         "CANDIDATE", None)


def test_ambiguous_product_row(db):
    """Scenario: 고를 수 없는 행 — 피더용·인입용 차단기가 모두 맞고 하위 항목으로 못 고르면
    확인 필요."""
    from rfp_agent.pipeline.products import load_products
    from rfp_agent.pipeline.selection import GroupContext, select
    from rfp_agent.pipeline.warranty import _candidate

    products = load_products(db)
    ctx = GroupContext("T1|III", "TS-SG III", "MV_EQUIP", um=24, frequencies={"50"}, isc_ka=25)
    pick = {label: select(products, ctx, None, label).product
            for label in ("Incoming", "Outgoing feeder", "Weight of complete 3-phase breaker")}
    assert pick["Incoming"].code == "VCB-SUSOL-24-25-2500"
    assert pick["Outgoing feeder"].code == "VCB-SUSOL-24-25-630"
    assert pick["Weight of complete 3-phase breaker"] is None
    mapping, fixed = _mapping(db)
    row = _candidate(1, 1, "weight", "kg", None, mapping, fixed)
    assert (row[2], row[8], row[9]) == (None, "EMPTY_REVIEW", "PRODUCT_AMBIGUOUS")


def test_loss_recalculation_is_team_assumption(db, spec):
    """Scenario: 가정 값이 섞인 결과 — 엔지니어가 넣은 손실값으로 다시 계산하면 팀 가정 표시."""
    from rfp_agent.pipeline.loss import recalculate

    run_id = run_once(db, [spec])
    clause = db.execute("SELECT min(requirement_id) FROM judgment WHERE run_id = %s",
                        (run_id,)).fetchone()[0]
    loss_id = db.execute(
        """INSERT INTO loss_calc (run_id, clause_requirement_id, price_noload, price_load,
                                  price_aux, price_unit, status, reason_code, is_assumed)
           VALUES (%s, %s, 4500, 3200, 1300, '$/kW', 'NEEDS_REVIEW', 'NO_LOSS_VALUE',
                   FALSE)
           RETURNING loss_calc_id""", (run_id, clause)).fetchone()[0]
    result = recalculate(db, loss_id, 60, 300, 8)
    assert (result["total_usd"], result["status"], result["is_assumed"]) == (
        1_240_400, "CALCULATED", True)
    assert result["formula"].endswith("= 1,240,400 $")


def test_same_input_same_judgments(db, spec):
    """CR-11 같은 입력이면 같은 판정·목록이다."""
    runs = [run_once(db, [spec]) for _ in range(2)]
    shape = [sorted((j["item_name_raw"], j["result"], j["product_code"])
                    for j in queries.run_judgments(db, r, limit=500)) for r in runs]
    texts = [[i["text_draft"] for i in queries.run_outputs(db, r)] for r in runs]
    assert shape[0] == shape[1] and texts[0] == texts[1]


def test_api_results_and_product_switch(db, spec, db_url, monkeypatch):
    """결과 조회 API와 비교 제품 바꾸기 API."""
    from fastapi.testclient import TestClient

    from rfp_agent.api.main import app
    from rfp_agent.config import get_settings

    run_id = run_once(db, [spec])
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    get_settings.cache_clear()
    try:
        client = TestClient(app)
        base = f"/api/runs/{run_id}"
        summary = client.get(base).json()
        assert summary["judgments"] > 0 and summary["deviation_candidates"] == 4
        groups = {g["label"]: g for g in client.get(f"{base}/equipment").json()}
        gis115 = next(g for label, g in groups.items() if "TS-115-GIS" in label)
        assert gis115["products"] == ["GIS-145"] and "GIS-145" in gis115["candidates"]
        bad = client.put(f"{base}/equipment/{gis115['equipment_group']}/product",
                         json={"product_code": "NO-SUCH"})
        assert bad.status_code == 400
        switched = client.put(f"{base}/equipment/{gis115['equipment_group']}/product",
                              json={"product_code": "GIS-145-P7"})
        assert switched.status_code == 200
        deviations = client.get(f"{base}/judgments",
                                params={"result": "DEVIATION_CANDIDATE"}).json()
        assert {j["product_code"] for j in deviations} == {"GIS-245-50", "GIS-145-P7"}
        outputs = client.get(f"{base}/outputs", params={"list_kind": "DEVIATION"}).json()
        assert outputs and all(i["locations"] for i in outputs)
        removed = client.post(f"{base}/actions", json={
            "target": "output_item", "target_id": outputs[0]["item_id"], "action": "REJECT",
            "reason": "목록에서 뺌"}).json()
        assert removed["submission_check"]["ar_codes"] == ["AR-07"]
        assert client.get(f"{base}/submission-check").json()["ar_codes"] == ["AR-07"]
        assert client.get(f"{base}/warranty").status_code == 200
        assert client.get(f"{base}/losses").json() == []
        assert client.get(f"{base}/proposals").json()
    finally:
        get_settings.cache_clear()


def test_locations_stay_within_the_run(db, spec, tmp_path):
    """CR-02 원문 위치는 그 실행의 문서만 낸다.

    앞 실행에서 같은 행이 다른 문서에 있었어도 섞이지 않는다."""
    copy = build_feeder_copy(tmp_path / "synthetic_feeder.docx")
    run_once(db, [spec, copy])
    run_id = run_once(db, [spec])
    files = {loc["file_no"] for i in queries.run_outputs(db, run_id) for loc in i["locations"]}
    files |= {loc["file_no"] for j in queries.run_judgments(db, run_id, limit=500)
              for loc in j["locations"]}
    assert files == {91}


def test_comparison_values_are_team_assumption(db, tmp_path):
    """Scenario: 팀 가정 비교값으로 한 판정 / 비교값 팀 가정 (CR-06).

    카탈로그 칸(정격 전압)은 팀 가정이 아니다.
    """
    doc = build_gis_spec(tmp_path / "synthetic_154kV_bundle_a.docx")

    def assumed(run_id):
        return dict(db.execute(
            "SELECT v.item_key, bool_or(j.is_assumed) FROM judgment j JOIN req_value v "
            "USING (value_id) WHERE j.run_id = %s AND j.product_value_raw IS NOT NULL "
            "GROUP BY v.item_key", (run_id,)))

    first = assumed(run_once(db, [doc]))
    assert first["gas_leakage_rate"] is True          # gas_leakage_percent, 비교값 가정 Y
    assert first["rated_voltage_um"] is False         # rated_voltage_kv, 카탈로그 값
    # 비교값 출처를 확인해 N으로 바꾸면 팀 가정 표시가 빠진다
    db.execute("UPDATE product_master SET comparison_values_assumed = 'N' "
               "WHERE product_code = 'GIS-170'")
    db.commit()
    assert assumed(run_once(db, [doc]))["gas_leakage_rate"] is False
