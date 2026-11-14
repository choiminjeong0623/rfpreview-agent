"""시연용 합성 RFP (change add-synthetic-risk-rfp).

명세 reference-data "시연용 합성 RFP"의 Scenario. 합성 RFP 원문은 저장소에 없다(data/private).
원문과 TEST_DATABASE_URL이 있을 때만 돈다(test_corpus와 같음).
파일 27은 generate_risk_rfp.py, 파일 28은 generate_switch_rfp.py로 만든다.
"""

import os

import pytest

from rfp_agent.config import get_settings
from rfp_agent.db.seed import seed_products
from rfp_agent.pipeline import classify as cls
from rfp_agent.pipeline import dictionaries, evaluation, queries, req_eval
from rfp_agent.pipeline.docx_reader import read_blocks
from rfp_agent.pipeline.run import RunContext, create_run, execute_run, switch_product

FILE_27 = get_settings().docx_dir / "RFP_Product_Master_Evaluative_EN_With_Risk_Clauses.docx"
FILE_28 = get_settings().docx_dir / "RFP_Product_Master_Evaluative_EN_With_Product_Switch.docx"
KEYS = get_settings().seed_dir / "answer_keys"

pytestmark = pytest.mark.skipif(
    not (FILE_27.exists() and os.environ.get("TEST_DATABASE_URL")),
    reason="합성 RFP 파일 27(data/private)이 없어 건너뜀 — generate_risk_rfp.py로 만든다",
)
VERSION = "test-dict-v1"


def test_synthetic_rfp_classification(db):
    """Scenario: 합성 RFP 분류 — 파일 27, 묶음 B, 요구 사양서, 판정 대상."""
    dicts = dictionaries.load(db)
    c = cls.classify(FILE_27.name, read_blocks(FILE_27), dicts.catalog, dicts.kind_rules)
    assert (c.file_no, c.bundle, c.doc_kind, c.judge_target) == (27, "B", "REQUIREMENT_SPEC", True)


def processed(db, path=FILE_27) -> int:
    """합성 RFP를 AI 없이 처리한다. 합성 RFP는 실제 제품표로 만들었으므로 실제 제품표로 판정한다."""
    seed_products(db, [get_settings().seed_dir / "products" / "product_master.csv"], replace=True)
    run_id = create_run(db, VERSION, None)
    assert execute_run(RunContext(db, VERSION, None, None), run_id, [path]) == "ENGINEER_REVIEW"
    return run_id


def test_risk_clause_variant(db):
    """Scenario: 위험 조항 변형 — 포괄 조항·범위 모호·값 불일치, 일탈 후보 10, 협조 요청."""
    run_id = processed(db)
    kinds = {k for (k,) in db.execute("SELECT DISTINCT risk_kind FROM risk_flag WHERE run_id = %s",
                                      (run_id,))}
    assert {"BLANKET", "OPEN_SCOPE", "VALUE_MISMATCH"} <= kinds
    assert queries.run_summary(db, run_id)["deviation_candidates"] == 10
    roles = {r for (r,) in db.execute("SELECT DISTINCT assignee_role FROM assignment "
                                      "WHERE run_id = %s", (run_id,))}
    assert {"COST", "QUALITY", "SALES"} <= roles


@pytest.mark.skipif(not FILE_28.exists(), reason="파일 28 없음 — generate_switch_rfp.py로 만든다")
def test_product_switch(db):
    """Scenario: 비교 제품 바꿔 보기 — 24 kV 차단기 후보 5개, 1250 A는 일탈 후보, 2000 A는 준수."""
    run_id = processed(db, FILE_28)
    doc = db.execute("SELECT d.file_no, d.bundle, d.doc_kind FROM run_document JOIN document d "
                     "USING (document_id) WHERE run_id = %s", (run_id,)).fetchone()
    assert doc == (28, "B", "REQUIREMENT_SPEC")
    [cb] = [g for g in queries.run_equipment(db, run_id) if "TS-24-CB" in g["label"]]
    assert (cb["family"], cb["products"], len(cb["candidates"])) == ("MV_EQUIP", None, 5)
    group = cb["equipment_group"]

    def current():
        return dict(db.execute(
            "SELECT v.item_key, j.result FROM judgment j JOIN req_value v USING (value_id) "
            "WHERE j.run_id = %s AND j.equipment_group = %s AND j.is_current",
            (run_id, group)).fetchall())

    assert len(current()) == 7 and set(current().values()) == {"NEEDS_REVIEW"}
    switch_product(RunContext(db, VERSION, None, None), run_id, group, "VCB-SUSOL-VH-20-40B13")
    low = current()
    assert low.pop("rated_current") == "DEVIATION_CANDIDATE" and set(low.values()) == {"COMPLY"}
    assert queries.run_summary(db, run_id)["deviation_candidates"] == 11
    switch_product(RunContext(db, VERSION, None, None), run_id, group, "VCB-SUSOL-VH-20-40B20")
    assert set(current().values()) == {"COMPLY"}
    assert queries.run_summary(db, run_id)["deviation_candidates"] == 10
    old = db.execute("SELECT count(*) FROM judgment WHERE run_id = %s AND equipment_group = %s "
                     "AND NOT is_current", (run_id, group)).fetchone()[0]
    assert old == 14                                  # 처음 7줄 + 1250 A 7줄


def load_keys(db) -> tuple[int, int]:
    req = req_eval.load_req_key(db, KEYS / "synthetic_rfp28_req.csv", "합성 RFP 28 요구사항",
                                FILE_28.stem, False)
    types = evaluation.load_key(db, KEYS / "synthetic_rfp28_type.csv", "합성 RFP 28 유형")
    return req.key_id, types.key_id


@pytest.mark.skipif(not FILE_28.exists(), reason="파일 28 없음 — generate_switch_rfp.py로 만든다")
def test_synthetic_answer_key_score(db):
    """Scenario: 합성 RFP 정답지 채점 — K1 65/65, K2 65/67, K3 30/30, K10 4/4, K13 42/42."""
    run_id = processed(db, FILE_28)
    req_key, type_key = load_keys(db)
    got = {m["code"]: (m["num"], m["den"])
           for m in evaluation.metrics(db, [run_id], type_key, req_key)["items"]}
    assert {k: got[k] for k in ("K1", "K2", "K3", "K10", "K13")} == {
        "K1": (65, 65), "K2": (65, 67), "K3": (30, 30), "K10": (4, 4), "K13": (42, 42)}
