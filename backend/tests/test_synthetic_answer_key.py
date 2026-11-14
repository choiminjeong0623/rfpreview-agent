"""시연용 합성 RFP 정답지 (change add-synthetic-answer-key).

명세 evaluation "시연용 합성 RFP 정답지"의 Scenario "합성 RFP 정답지 넣기".
정답지 CSV는 저장소에 있어 원문 없이 돈다.
채점 Scenario는 파일 28 원문이 있어야 해서 tests/test_synthetic_rfps.py에 있다.
"""

from rfp_agent.config import get_settings
from rfp_agent.pipeline import evaluation, req_eval

KEYS = get_settings().seed_dir / "answer_keys"
DOC = "RFP_Product_Master_Evaluative_EN_With_Product_Switch"


def test_load_synthetic_answer_keys(db):
    """Scenario: 합성 RFP 정답지 넣기 — 요구사항 69줄(파일 28), 유형 65줄, Claude 초안."""
    req = req_eval.load_req_key(db, KEYS / "synthetic_rfp28_req.csv", "합성 RFP 28 요구사항", DOC,
                                False)
    types = evaluation.load_key(db, KEYS / "synthetic_rfp28_type.csv", "합성 RFP 28 유형")
    assert (req.rows, req.skipped, types.rows, types.skipped) == (69, [], 65, [])
    listed = {k["key_name"]: k for k in evaluation.keys(db)}
    reqs = listed["합성 RFP 28 요구사항"]
    assert (reqs["key_kind"], reqs["doc_name"]) == ("REQ", DOC)
    assert {listed[n]["made_by"] for n in ("합성 RFP 28 요구사항", "합성 RFP 28 유형")} \
        == {"CLAUDE_DRAFT"}
    assert listed["합성 RFP 28 유형"]["human_checked"] == 0
    kinds = dict(db.execute("SELECT expected, count(*) FROM answer_key_row WHERE key_id = %s "
                            "GROUP BY expected", (req.key_id,)).fetchall())
    assert kinds == {"REQUIREMENT": 65, "BLANKET": 2, "OPEN_SCOPE": 1, "VALUE_MISMATCH": 1}
