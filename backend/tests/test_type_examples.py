"""사람이 고친 유형과 AI 유형 질문의 예시.

change add-type-examples, 명세 requirement-extraction.
"""

import csv

import pytest
from docx import Document

from rfp_agent.pipeline import req_eval, review, run_log
from rfp_agent.pipeline.run import RunContext, create_run, execute_run
from tests.conftest import FakeLLM
from tests.docx_factory import build_gis_spec
from tests.test_role_assignment import sent

VERSION = "test-dict-v1"
FIXED = "The supplier shall demonstrate the dielectric strength of each bay before dispatch."
NEAR = "The supplier shall demonstrate the dielectric strength of every bay prior to dispatch."
FAR = "Spare keys for every cubicle door lock shall be handed over to the owner."


def spec_with(path, sentence):
    build_gis_spec(path)
    doc = Document(str(path))
    doc.add_paragraph(sentence)
    doc.save(str(path))
    return path


def run(db, tmp_path, name, sentence, llm):
    (tmp_path / name).mkdir()
    path = spec_with(tmp_path / name / "synthetic_154kV_GIS_spec.docx", sentence)
    run_id = create_run(db, VERSION, llm)
    assert execute_run(RunContext(db, VERSION, llm, None), run_id, [path]) == "ENGINEER_REVIEW"
    return run_id


def requirement_of(db, run_id, text):
    return db.execute(
        "SELECT q.requirement_id FROM requirement q JOIN run_document rd USING (document_id) "
        "WHERE rd.run_id = %s AND q.text_raw = %s", (run_id, text)).fetchone()[0]


def primary(db, req_id):
    return db.execute("SELECT type_code, decided_by FROM requirement_type_tag "
                      "WHERE requirement_id = %s AND is_primary", (req_id,)).fetchone()


@pytest.fixture
def fixed_run(db, tmp_path):
    """문서 A의 미분류 줄을 엔지니어가 시험으로 고친 검토."""
    run_id = run(db, tmp_path, "a", FIXED, FakeLLM())
    req = requirement_of(db, run_id, FIXED)
    assert primary(db, req) is None                       # 규칙·AI 모두 미분류
    engineer = review.default_user(db, "ENGINEER")
    result = review.set_type(db, run_id, req, "TEST", "입회 시험 요구", engineer)
    assert (result["before"], result["after"]) == ("NONE", "TEST")
    return run_id, req


def test_engineer_fixes_type(db, fixed_run):
    """Scenario: 엔지니어가 유형 고치기 — 시험·사람, 이력 미분류 → 시험, 품질 담당 요청."""
    run_id, req = fixed_run
    assert primary(db, req) == ("TEST", "HUMAN")
    [entry] = [h for h in review.history(db, run_id, "requirement") if h["target_id"] == req]
    assert entry["action"] == "EDIT" and entry["reason"] == "입회 시험 요구"
    assert (entry["before_value"]["type_code"], entry["after_value"]["type_code"]) == \
        ("NONE", "TEST")
    assert any(req in t["requirement_ids"] for t in sent(db, run_id, "QUALITY"))


def test_other_role_cannot_fix_type(db, fixed_run):
    """Scenario: 다른 역할은 못 고침 — 견적 담당은 거절, 유형 그대로."""
    run_id, req = fixed_run
    with pytest.raises(review.ReviewError, match="엔지니어와 승인자만"):
        review.set_type(db, run_id, req, "COST", None, review.default_user(db, "COST"))
    assert primary(db, req) == ("TEST", "HUMAN")


def typing_prompts(llm):
    return [p for p in llm.prompts if "유형 하나를 고른다" in p]


def test_near_human_example(db, tmp_path, fixed_run):
    """Scenario: 가까운 사람 예시 — 그 줄에 예시 문장과 시험, 실행 기록 유형 예시 1 이상."""
    llm = FakeLLM()
    run_id = run(db, tmp_path, "b", NEAR, llm)
    [line] = [x for p in typing_prompts(llm) for x in p.splitlines() if NEAR in x]
    assert f'(사람이 고른 예: "{FIXED}" → TEST)' in line
    [row] = [r for r in run_log.run_log(db) if r["run_id"] == run_id]
    assert row["type_examples"] >= 1


def test_answer_key_sentence_is_not_example(db, tmp_path, fixed_run):
    """Scenario: 정답지 문장은 예시가 아님."""
    key = tmp_path / "key.csv"
    with key.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["번호", "text", "expected", "value", "unit", "note"])
        w.writerow([1, FIXED, "REQUIREMENT", "", "", ""])
    req_eval.load_req_key(db, key, "예시 빼기", "synthetic_154kV_GIS")
    llm = FakeLLM()
    run(db, tmp_path, "b", NEAR, llm)
    assert not any("(사람이 고른 예:" in p for p in typing_prompts(llm))


def test_far_line_has_no_example(db, tmp_path, fixed_run):
    """Scenario: 먼 줄에는 예시 없음."""
    llm = FakeLLM()
    run(db, tmp_path, "b", FAR, llm)
    [line] = [x for p in typing_prompts(llm) for x in p.splitlines() if FAR in x]
    assert "(사람이 고른 예:" not in line


def test_vector_failure_asks_without_examples(db, tmp_path, fixed_run):
    """Scenario: 벡터 실패 — 예시 없이 묻고 담당자 확인 단계까지."""
    llm = FakeLLM()
    llm.embed_fail = True
    run_id = run(db, tmp_path, "b", NEAR, llm)          # run()이 담당자 확인 단계를 확인
    assert typing_prompts(llm) and not any("(사람이 고른 예:" in p for p in typing_prompts(llm))
    [row] = [r for r in run_log.run_log(db) if r["run_id"] == run_id]
    assert row["type_examples"] == 0
