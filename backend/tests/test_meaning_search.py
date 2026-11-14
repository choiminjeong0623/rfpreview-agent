"""뜻으로 찾기: 벡터 저장, 사전 추가 후보, 항목 연결 후보, 뜻이 비슷한 지난 확정.

change add-meaning-search, 명세 review-run·risk-detection·reference-data·review-approval.
"""

import pytest
from docx import Document

from rfp_agent.llm.client import LLMFailure, embed_with_retry
from rfp_agent.pipeline import meaning, queries, review, rule_edit
from rfp_agent.pipeline.run import RunContext, create_run, execute_run
from tests.conftest import FakeLLM, word_vector
from tests.docx_factory import GIS_115_ROWS, _datasheet, build_gis_spec

VERSION = "test-dict-v1"
PARAPHRASE = ("Any item not listed in the deviation list shall be considered as fully "
              "complied with by the Vendor.")


def run(db, paths, llm):
    run_id = create_run(db, VERSION, llm)
    assert execute_run(RunContext(db, VERSION, llm, None), run_id, paths) == "ENGINEER_REVIEW"
    return run_id


def risk_count(db, run_id):
    return db.execute("SELECT count(*) FROM risk_flag WHERE run_id = %s", (run_id,)).fetchone()[0]


def gis_with_paraphrase(path):
    build_gis_spec(path)
    doc = Document(str(path))
    doc.add_paragraph(PARAPHRASE)
    doc.save(str(path))
    return path


def datasheet(path, rows):
    """판정 대상(묶음 A) 데이터시트. 파일 이름은 문서 목록 91번(synthetic_judgment)."""
    doc = Document()
    doc.add_paragraph("SCHEDULE OF TECHNICAL DATA")
    doc.add_paragraph("1. DATA SHEET")
    _datasheet(doc, "TS-230-GIS", rows)
    _datasheet(doc, "TS-115-GIS", GIS_115_ROWS)
    doc.save(str(path))
    return path


BASE_ROWS = [
    ["1", "Rated voltage", "kV", "245", ""],
    ["2", "Rated frequency", "Hz", "50", ""],
    ["3", "Rated normal current of main busbar", "A", "4000", ""],
]


def test_vectors_are_reused(db, tmp_path):
    """Scenario: 같은 글은 다시 묻지 않음 — 두 번째 검토는 벡터를 묻지 않고 같은 후보."""
    path = gis_with_paraphrase(tmp_path / "synthetic_154kV_GIS_spec.docx")
    first_llm, second_llm = FakeLLM(), FakeLLM()
    first = run(db, [path], first_llm)
    second = run(db, [path], second_llm)
    assert first_llm.embedded and not getattr(second_llm, "embedded", [])
    a, b = (meaning.risk_candidates(db, r) for r in (first, second))
    assert [(c["text_raw"], c["score"]) for c in a["items"]] == \
        [(c["text_raw"], c["score"]) for c in b["items"]]
    assert a["status"] == b["status"] == "DONE"


def test_no_ai_skips_meaning(db, tmp_path):
    """Scenario: 언어 모델 없음 — 담당자 확인 단계, 상태 "안 함", 후보 없음."""
    path = gis_with_paraphrase(tmp_path / "synthetic_154kV_GIS_spec.docx")
    run_id = run(db, [path], None)
    assert meaning.risk_candidates(db, run_id) == {"status": "NO_AI", "items": []}


def test_embed_failure_does_not_stop_run(db, tmp_path):
    """Scenario: 벡터 요청 실패 — 담당자 확인 단계, 상태 "건너뜀"."""
    path = gis_with_paraphrase(tmp_path / "synthetic_154kV_GIS_spec.docx")
    llm = FakeLLM()
    llm.embed_fail = True
    run_id = run(db, [path], llm)
    assert meaning.risk_candidates(db, run_id) == {"status": "SKIPPED", "items": []}
    assert len(llm.embedded) == 3 * len(set(llm.embedded))   # 첫 묶음을 재시도 2번 (CR-12)


def test_embed_retry_and_config_error():
    """벡터 요청도 연결 오류만 다시 시도하고 키·모델 오류는 바로 멈춘다."""
    class KeyError400(Exception):
        code = 403

    class Bad(FakeLLM):
        def embed(self, texts):
            raise KeyError400("키 오류")

    with pytest.raises(LLMFailure, match="설정"):
        embed_with_retry(Bad(), ["a"])
    assert embed_with_retry(FakeLLM(), ["a b"]) == [word_vector("a b")]


def test_paraphrased_blanket_clause(db, tmp_path):
    """Scenario: 다른 말로 쓴 포괄 조항.

    사전에 걸린 "deemed to be accepted" 문장과 뜻이 가까운 문장이 후보로 나오고
    위험 조건 수는 그대로.
    """
    (tmp_path / "a").mkdir()
    base = run(db, [build_gis_spec(tmp_path / "a" / "synthetic_154kV_GIS_spec.docx")], FakeLLM())
    path = gis_with_paraphrase(tmp_path / "synthetic_154kV_GIS_spec.docx")
    run_id = run(db, [path], FakeLLM())
    assert risk_count(db, run_id) == risk_count(db, base)
    items = meaning.risk_candidates(db, run_id)["items"]
    [cand] = items
    assert cand["text_raw"] == PARAPHRASE
    assert "deemed to be accepted" in cand["near_text"] and cand["target"] == "BLANKET"
    assert cand["score"] >= meaning.RISK_MIN and cand["locations"]


def test_unrelated_sentences_have_no_candidates(db, tmp_path):
    """Scenario: 관계없는 문장 — 위험 조건 문장과 뜻이 먼 문장만 있으면 후보 없음."""
    run_id = run(db, [build_gis_spec(tmp_path / "synthetic_154kV_GIS_spec.docx")], FakeLLM())
    result = meaning.risk_candidates(db, run_id)
    assert result == {"status": "DONE", "items": []}


NEW_NAME = "Busbar ampacity"


@pytest.fixture
def item_run(db, tmp_path):
    """사전에 없는 표 항목 이름이 든 데이터시트. 그 이름의 벡터는 정격 전류 표현과 같게 둔다."""
    path = datasheet(tmp_path / "synthetic_judgment.docx",
                     [*BASE_ROWS, ["4", NEW_NAME, "A", "4000", ""]])
    llm = FakeLLM()
    llm.vectors = {NEW_NAME: word_vector("Rated normal current")}
    return run(db, [path], llm)


def test_item_link_candidate(db, item_run):
    """Scenario: 사전에 없는 표 항목 이름 — 연결 후보에 이름, 항목 rated_current, 점수."""
    [cand] = [c for c in meaning.item_candidates(db) if c["text_raw"] == NEW_NAME]
    assert cand["target"] == "rated_current" and cand["score"] >= meaning.ITEM_MIN
    assert cand["score"] - (cand["second_score"] or 0) >= meaning.ITEM_GAP
    assert cand["run_id"] == item_run and cand["locations"]


def test_accept_item_link(db, item_run):
    """Scenario: 후보 받아들이기 — 같은 뜻 표현에 더해지고 고침 이력 1건, 목록에서 빠짐."""
    [cand] = [c for c in meaning.item_candidates(db) if c["text_raw"] == NEW_NAME]
    before = len(rule_edit.edits(db, "items"))
    edit = meaning.accept_item(db, cand["candidate_id"])
    assert NEW_NAME in edit["after_value"]["aliases"]
    assert len(rule_edit.edits(db, "items")) == before + 1
    aliases = [a for (a,) in db.execute(
        "SELECT alias_text FROM item_alias WHERE item_key = 'rated_current'")]
    assert NEW_NAME in aliases
    assert not [c for c in meaning.item_candidates(db) if c["text_raw"] == NEW_NAME]
    with pytest.raises(review.ReviewError):
        meaning.accept_item(db, cand["candidate_id"])


def test_hide_item_link_stays_hidden(db, item_run, tmp_path):
    """숨긴 후보는 다른 검토에서도 다시 보이지 않는다."""
    [cand] = [c for c in meaning.item_candidates(db) if c["text_raw"] == NEW_NAME]
    meaning.hide_item(db, cand["candidate_id"])
    (tmp_path / "x").mkdir()
    path = datasheet(tmp_path / "x" / "synthetic_judgment.docx",
                     [*BASE_ROWS, ["4", NEW_NAME, "A", "3150", ""]])
    llm = FakeLLM()
    llm.vectors = {NEW_NAME: word_vector("Rated normal current")}
    run(db, [path], llm)
    assert not [c for c in meaning.item_candidates(db) if c["text_raw"] == NEW_NAME]


def test_close_runner_up_is_not_a_candidate():
    """Scenario: 두 항목이 비슷하게 가까움 — 1등과 2등 차가 0.03보다 작으면 후보가 아니다."""
    pool = [("rated_current", "Rated current", [1.0, 0.0]),
            ("rated_frequency", "Rated frequency", [0.99, 0.141])]
    assert meaning._item_candidate([1.0, 0.0], pool) is None
    far = [("rated_current", "Rated current", [1.0, 0.0]),
           ("rated_frequency", "Rated frequency", [0.8, 0.6])]
    found = meaning._item_candidate([1.0, 0.0], far)
    assert found[0] == "rated_current" and found[3] == "rated_frequency"


def act(db, run_id, judgment_id, action, value=None, reason=None):
    review.act(RunContext(db, VERSION, FakeLLM(), None), run_id, "judgment", judgment_id,
               action, value, reason)


def main_busbar(db, run_id):
    return db.execute(
        """SELECT j.judgment_id FROM judgment j JOIN requirement q USING (requirement_id)
            WHERE j.run_id = %s AND j.is_current AND q.text_raw LIKE '%%main busbar%%'
            ORDER BY j.judgment_id LIMIT 1""", (run_id,)).fetchone()[0]


@pytest.fixture
def confirmed_first(db, tmp_path):
    (tmp_path / "1").mkdir()
    first = run(db, [datasheet(tmp_path / "1" / "synthetic_judgment.docx", BASE_ROWS)],
                FakeLLM())
    old = main_busbar(db, first)
    act(db, first, old, "EDIT", {"result": "DEVIATION_CANDIDATE"}, "모선 정격이 다름")
    return first


RENAMED = [*BASE_ROWS[:2], ["3", "Rated normal current of the main busbar", "A", "4000", ""]]


def test_meaning_hint_for_reworded_line(db, tmp_path, confirmed_first):
    """Scenario: 글자는 다르고 뜻이 같은 지난 확정 — "뜻이 비슷함"과 점수, 새 판정 값은 그대로."""
    (tmp_path / "2").mkdir()
    second = run(db, [datasheet(tmp_path / "2" / "synthetic_judgment.docx", RENAMED)], FakeLLM())
    new = main_busbar(db, second)
    row = {j["judgment_id"]: j for j in queries.run_judgments(db, second, limit=500)}[new]
    past = row["past_decision"]
    assert past["match"] == "MEANING" and past["score"] >= meaning.MEMORY_MIN
    assert past["result"] == "DEVIATION_CANDIDATE" and past["run_id"] == confirmed_first
    assert past["same"] is (row["result"] == "DEVIATION_CANDIDATE")
    assert row["review_status"] == "CANDIDATE"          # 힌트는 판정·확인 상태를 바꾸지 않음


def test_far_meaning_has_no_hint(db, tmp_path, confirmed_first):
    """Scenario: 뜻이 먼 줄 — 요구값·제품은 같아도 코사인이 0.92보다 작으면 지난 확정 없음."""
    (tmp_path / "3").mkdir()
    llm = FakeLLM()
    text = "3 / Rated normal current of the main busbar / A / 4000"
    llm.vectors = {text: [0.0] * 255 + [1.0]}
    second = run(db, [datasheet(tmp_path / "3" / "synthetic_judgment.docx", RENAMED)], llm)
    new = main_busbar(db, second)
    assert db.execute("SELECT text_raw FROM requirement q JOIN judgment j USING (requirement_id) "
                      "WHERE j.judgment_id = %s", (new,)).fetchone()[0] == text
    row = {j["judgment_id"]: j for j in queries.run_judgments(db, second, limit=500)}[new]
    assert row["past_decision"] is None
