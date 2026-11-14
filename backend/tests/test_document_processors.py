"""문서 종류별 처리기, 처리 뒤 점검과 한 번 다시 처리, 문서 병렬 처리.

change add-document-processors (C1), update-partial-reprocess (떨어진 부분만 다시 묻기).

명세 document-intake "문서 종류별 처리기"·"처리 뒤 점검과 한 번 다시 처리"·"문서 병렬 처리",
requirement-extraction "AI 질문의 문서 종류 설명", review-run "다시 처리한 문서 수"의 Scenario.
"""

import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from docx import Document

from rfp_agent.pipeline import dictionaries, queries, run_control
from rfp_agent.pipeline import run as run_mod
from rfp_agent.pipeline.document import process_document
from rfp_agent.pipeline.run import RunContext, create_run, execute_run
from rfp_agent.pipeline.run_log import run_log
from tests.conftest import FakeLLM
from tests.docx_factory import build_gis_spec, build_judgment_spec

VERSION = "test-dict-v1"
LABEL = "RFP의 한 절에서"
TYPE = "유형 하나를 고른다"


def letters(path: Path) -> Path:
    """표 없이 요구 문장만 있는 문서 (입찰 서식 이름이면 점검에 걸린다)."""
    doc = Document()
    doc.add_paragraph("INSTRUCTIONS")
    doc.add_paragraph("1. GENERAL")
    doc.add_paragraph("The bidder shall submit the completed forms with the bid.")
    doc.add_paragraph("The equipment shall withstand the specified dielectric tests.")
    doc.add_paragraph("The contractor shall provide spare parts for five years of operation.")
    doc.add_paragraph("2. DOCUMENTS")
    doc.add_paragraph("The bidder shall provide the type test reports for all equipment.")
    doc.add_paragraph("The vendor shall supply operation and maintenance manuals in English.")
    doc.add_paragraph("All drawings shall be submitted for approval before manufacture.")
    doc.add_paragraph("3. PACKING")
    doc.add_paragraph("All equipment shall be packed for sea transport and long storage.")
    doc.add_paragraph("Each package shall be marked with the contract number and weight.")
    doc.save(str(path))
    return path


def no_tests(path: Path) -> Path:
    """시험 유형 규칙에 걸리는 낱말이 없는 요구 문장 문서 (시험 사양서 이름이면 점검에 걸린다).

    협조 요청 유형 낱말(spare parts 등)이 든 문장은 AI에 묻지 않아 절이 통째로 떨어지지 않으므로
    넣지 않는다 (update-ai-label-keep-handoff).
    """
    doc = Document()
    doc.add_paragraph("1. GENERAL")
    doc.add_paragraph("The contractor shall paint all steel parts before the final inspection.")
    doc.add_paragraph("The vendor shall supply operation and maintenance manuals in English.")
    doc.add_paragraph("2. PACKING")
    doc.add_paragraph("All equipment shall be packed for sea transport and long storage.")
    doc.add_paragraph("Each package shall be marked with the contract number and weight.")
    doc.add_paragraph("The bidder shall submit the completed forms with the bid.")
    doc.add_paragraph("All drawings shall be submitted for approval before manufacture.")
    doc.add_paragraph("The contractor shall keep the site clean during the installation work.")
    doc.add_paragraph("The supplier shall nominate one engineer as the single point of contact.")
    doc.save(str(path))
    return path


def boq(path: Path, rows: bool = True) -> Path:
    """물량표: 품목·수량·단위 표와 안내 문장 몇 줄 (rows=False면 표 없이 문장만)."""
    doc = Document()
    doc.add_paragraph("BILL OF QUANTITIES")
    doc.add_paragraph("1. GENERAL")
    doc.add_paragraph("The bidder shall quote for all items listed in this schedule.")
    doc.add_paragraph("Quantities shall be verified by the bidder before the bid submission.")
    doc.add_paragraph("2. SCHEDULE")
    if rows:
        table = doc.add_table(rows=0, cols=4)
        for r in [["Item", "Description", "Qty", "Unit"], ["1", "145 kV GIS bay", "4", "set"],
                  ["2", "Local control cubicle", "4", "set"], ["3", "Spare parts", "1", "lot"]]:
            cells = table.add_row().cells
            for c, v in zip(cells, r, strict=True):
                c.text = v
    for n in range(6):
        doc.add_paragraph(f"Note {n + 1}: The unit of each item shall be as in the schedule.")
    doc.save(str(path))
    return path


class HintMisleads(FakeLLM):
    """문서 종류 설명이 붙은 문장 구분 질문에는 모두 작성 규칙이라고 답하는 대역."""

    def generate_json(self, prompt: str, schema: dict) -> dict:
        answer = super().generate_json(prompt, schema)
        if "labels" in answer and prompt.startswith("문서 종류:"):
            answer["labels"] = [{"n": a["n"], "v": "WRITING_RULE"} for a in answer["labels"]]
        return answer


def document_row(conn, document_id):
    return conn.execute("SELECT processor, process_check, reprocessed, needs_review FROM document "
                        "WHERE document_id = %s", (document_id,)).fetchone()


def reprocessed_lines(conn, document_id):
    return conn.execute("SELECT reprocessed_lines FROM document WHERE document_id = %s",
                        (document_id,)).fetchone()[0]


def process(conn, path, llm):
    return process_document(conn, path, dictionaries.load(conn), VERSION, llm, None)


def test_bid_form_uses_bid_form_processor(db, tmp_path):
    """Scenario: 입찰 서식은 입찰 서식 처리기 — 질문에 입찰 서식 설명, 점검 통과."""
    llm = FakeLLM()
    result = process(db, build_gis_spec(tmp_path / "Bidding Forms_gis.docx"), llm)
    assert document_row(db, result.document_id)[:3] == ("BID_FORM", None, False)
    labels = [p for p in llm.prompts if LABEL in p]
    assert labels and all(p.startswith("문서 종류: 입찰 서식") for p in labels)


def test_unknown_uses_general_processor(db, tmp_path):
    """Scenario: 종류 모름은 일반 처리기 — 질문에 문서 종류 설명이 없다."""
    llm = FakeLLM()
    result = process(db, letters(tmp_path / "misc_notes.docx"), llm)
    assert document_row(db, result.document_id)[0] == "GENERAL"
    asked = [p for p in llm.prompts if LABEL in p or TYPE in p]
    assert asked and not any(p.startswith("문서 종류:") for p in asked)


def test_failed_test_spec_reasks_unknown_types(db, tmp_path):
    """Scenario: 점검에 걸린 시험 사양서 — 문장 구분은 그대로, 유형 못 정한 줄만 설명 없이 다시."""
    llm = FakeLLM()
    result = process(db, no_tests(tmp_path / "testing_plain.docx"), llm)
    processor, check, again, review = document_row(db, result.document_id)
    assert (processor, again, review) == ("TEST_SPEC", True, True)
    assert check == "시험 사양서인데 시험 유형 줄이 하나도 없습니다"
    labels = [p for p in llm.prompts if LABEL in p]
    assert labels and all(p.startswith("문서 종류: 시험 사양서") for p in labels)  # 다시 안 물음
    typed = [p for p in llm.prompts if TYPE in p]
    first, again_asked = typed[0], typed[1:]
    assert first.startswith("문서 종류: 시험 사양서")
    assert again_asked and not any(p.startswith("문서 종류:") for p in again_asked)
    unknown = len(re.findall(r"^\d+\. ", first, re.MULTILINE))     # 처음 물어 모두 NONE인 줄
    assert reprocessed_lines(db, result.document_id) == unknown == result.reprocessed_lines > 0
    assert db.execute("SELECT count(*) FROM document").fetchone()[0] == 1


def test_failed_requirement_spec_reasks_dropped_sections(db, tmp_path):
    """Scenario: 점검에 걸린 요구 사양서 — 빠진 절만 설명 없이 다시, 요구사항으로 저장."""
    llm = HintMisleads()
    result = process(db, no_tests(tmp_path / "general_specification.docx"), llm)
    processor, check, again, review = document_row(db, result.document_id)
    assert (processor, again, review) == ("REQUIREMENT_SPEC", True, True)
    assert check == "요구 사양서인데 요구사항 줄이 하나도 없습니다"
    labels = [p for p in llm.prompts if LABEL in p]
    hinted = [p for p in labels if p.startswith("문서 종류: 기술 요구 사양서")]
    assert hinted and len(labels) == 2 * len(hinted)      # 떨어진 절(여기선 둘 다)만 한 번 더
    assert reprocessed_lines(db, result.document_id) == 8
    kinds = db.execute("SELECT req_kind, extracted_by FROM requirement WHERE document_id = %s",
                       (result.document_id,)).fetchall()
    assert len(kinds) == 8 and all(k == ("REQUIREMENT", "RULE") for k in kinds)


def test_failed_bid_form_not_reasked(db, tmp_path):
    """Scenario: 점검에 걸린 입찰 서식 — AI에 다시 묻지 않고 처리기·이유·확인 필요만."""
    llm = FakeLLM()
    result = process(db, letters(tmp_path / "Bidding Forms_letters.docx"), llm)
    assert document_row(db, result.document_id) == (
        "BID_FORM", "입찰 서식인데 표 칸 요구값이 하나도 없습니다", False, True)
    assert result.reprocessed is False and reprocessed_lines(db, result.document_id) == 0
    asked = [p for p in llm.prompts if LABEL in p or TYPE in p]
    assert asked and all(p.startswith("문서 종류: 입찰 서식") for p in asked)


def test_boq_uses_boq_processor(db, tmp_path):
    """Scenario: 물량표는 물량표 처리기 — 종류·처리기 물량표, 질문에 물량표 설명, 점검 통과."""
    llm = FakeLLM()
    result = process(db, boq(tmp_path / "BOQ_substation.docx"), llm)
    kind = db.execute("SELECT doc_kind FROM document WHERE document_id = %s",
                      (result.document_id,)).fetchone()[0]
    assert kind == "BOQ"
    assert document_row(db, result.document_id)[:3] == ("BOQ", None, False)
    labels = [p for p in llm.prompts if LABEL in p]
    assert labels and all(p.startswith("문서 종류: 물량표(BOQ)") for p in labels)


def test_boq_without_table(db, tmp_path):
    """Scenario: 표가 없는 물량표 — 다시 묻지 않고 처리기·이유·확인 필요만."""
    llm = FakeLLM()
    result = process(db, boq(tmp_path / "BOQ_substation.docx", rows=False), llm)
    assert document_row(db, result.document_id) == (
        "BOQ", "물량표인데 표 줄이 하나도 없습니다", False, True)
    asked = [p for p in llm.prompts if LABEL in p or TYPE in p]
    assert asked and all(p.startswith("문서 종류: 물량표(BOQ)") for p in asked)


def test_failed_check_without_ai(db, tmp_path):
    """Scenario: AI 없이 점검에 걸림 — 다시 처리하지 않고 이유·확인 필요만."""
    result = process(db, no_tests(tmp_path / "testing_plain.docx"), None)
    assert document_row(db, result.document_id) == (
        "TEST_SPEC", "시험 사양서인데 시험 유형 줄이 하나도 없습니다", False, True)


def test_passing_check(db, tmp_path):
    """Scenario: 점검을 통과한 문서 — 이유가 비고 다시 처리하지 않는다."""
    result = process(db, build_gis_spec(tmp_path / "Bidding Forms_gis.docx"), None)
    processor, check, again, _ = document_row(db, result.document_id)
    assert (processor, check, again) == ("BID_FORM", None, False)


def test_test_spec_type_question_has_hint(db, tmp_path):
    """Scenario: 시험 사양서 유형 질문 — 질문 첫머리에 시험 사양서 설명."""
    llm = FakeLLM()
    process(db, letters(tmp_path / "testing_procedure.docx"), llm)
    typed = [p for p in llm.prompts if TYPE in p]
    assert typed and typed[0].startswith("문서 종류: 시험 사양서")


def workers(monkeypatch, n):
    monkeypatch.setattr(run_mod, "get_settings", lambda: SimpleNamespace(rfp_doc_workers=n))


def run_with(db, version, paths):
    run_id = create_run(db, version, None)
    assert execute_run(RunContext(db, version, None, None), run_id, paths) == "ENGINEER_REVIEW"
    return run_id


def summary(db, run_id):
    ids = [d["document_id"] for d in queries.run_documents(db, run_id)]
    reqs, dedup = db.execute("SELECT count(*), count(dedup_of) FROM requirement "
                             "WHERE document_id = ANY(%s)", (ids,)).fetchone()
    reps = db.execute("""SELECT d.file_name FROM requirement r
                           JOIN requirement p ON p.requirement_id = r.dedup_of
                           JOIN document d ON d.document_id = p.document_id
                          WHERE r.document_id = ANY(%s) GROUP BY 1 ORDER BY 1""",
                      (ids,)).fetchall()
    pairs = db.execute("SELECT count(*) FROM document_pair WHERE document_id_a = ANY(%s)",
                       (ids,)).fetchone()[0]
    return reqs, dedup, reps, pairs, queries.run_summary(db, run_id)["judgments"]


def test_parallel_matches_sequential(db, spec, tmp_path, monkeypatch):
    """Scenario: 병렬과 차례 결과가 같음 — 요구·묶음·쌍 후보·판정 수."""
    second = build_judgment_spec(tmp_path / "second_datasheet.docx")
    workers(monkeypatch, 1)
    seq = summary(db, run_with(db, "v-seq", [spec, second]))
    workers(monkeypatch, 2)
    par = summary(db, run_with(db, "v-par", [spec, second]))
    assert seq == par
    assert seq[1] > 0 and seq[2] == [(spec.name,)]     # 두 번째 문서 줄이 첫 문서 줄로 묶임


def test_parallel_one_document_fails(db, spec, tmp_path, monkeypatch):
    """Scenario: 한 문서 실패 — 실패로 끝나고 첫 문서는 저장되어 다시 시도 때 다시 쓰인다."""
    workers(monkeypatch, 2)
    second = build_judgment_spec(tmp_path / "second_datasheet.docx")
    real = run_mod.process_document
    calls = []

    def fail_second(conn, path, *args, **kwargs):
        calls.append(path.name)
        if path.name == second.name and calls.count(second.name) == 1:
            raise RuntimeError("두 번째 문서에서 멈춤")
        return real(conn, path, *args, **kwargs)

    monkeypatch.setattr(run_mod, "process_document", fail_second)
    run_id = create_run(db, VERSION, None)
    assert execute_run(RunContext(db, VERSION, None, None), run_id, [spec, second]) == "FAILED"
    [(first_doc,)] = db.execute("SELECT document_id FROM document").fetchall()
    paths, choices = run_control.prepare_retry(db, run_id, None)
    assert execute_run(RunContext(db, VERSION, None, None), run_id, paths, choices) \
        == "ENGINEER_REVIEW"
    docs = [d["document_id"] for d in queries.run_documents(db, run_id)]
    assert first_doc in docs and len(docs) == 2


def run_log_row(db, paths):
    llm = FakeLLM()
    run_id = create_run(db, VERSION, llm)
    assert execute_run(RunContext(db, VERSION, llm, None), run_id, paths) == "ENGINEER_REVIEW"
    [row] = [r for r in run_log(db) if r["run_id"] == run_id]
    return run_id, row


def test_run_log_counts_reprocessed(db, spec, tmp_path):
    """Scenario: 다시 처리한 문서가 있는 검토 — 문서 수 1, 줄 수는 그 문서에 남은 줄 수."""
    run_id, row = run_log_row(db, [spec, no_tests(tmp_path / "testing_plain.docx")])
    [doc] = [d for d in queries.run_documents(db, run_id) if d["reprocessed"]]
    assert row["documents_reprocessed"] == 1
    assert row["lines_reprocessed"] == doc["reprocessed_lines"] > 0


def test_run_log_not_reasked(db, spec, tmp_path):
    """Scenario: 다시 묻지 않은 점검 — 입찰 서식만 걸린 검토는 문서 수·줄 수 모두 0."""
    _, row = run_log_row(db, [spec, letters(tmp_path / "Bidding Forms_letters.docx")])
    assert (row["documents_reprocessed"], row["lines_reprocessed"]) == (0, 0)


@pytest.mark.parametrize("kind", ["REQUIREMENT_SPEC", "PURCHASE_SPEC", "SUPPLIER_SPEC", "BOQ"])
def test_every_kind_has_check(kind):
    """처리기 표: 종류마다 설명과 점검이 있다 (일반 처리기는 둘 다 없음)."""
    from rfp_agent.pipeline.processors import GENERAL, processor_for
    proc = processor_for(kind)
    assert proc.hint and proc.check and proc is not GENERAL
    assert processor_for("UNKNOWN") is GENERAL and GENERAL.check is None and GENERAL.fix is None


def test_fix_only_where_ai_can_change_check():
    """처리기 표: 다시 물을 단계는 AI 답이 점검을 바꿀 수 있는 곳만 (update-partial-reprocess)."""
    from rfp_agent.pipeline.processors import LABEL as FIX_LABEL
    from rfp_agent.pipeline.processors import TYPE as FIX_TYPE
    from rfp_agent.pipeline.processors import processor_for
    assert {k: processor_for(k).fix for k in ["BID_FORM", "REQUIREMENT_SPEC", "TEST_SPEC",
                                               "PURCHASE_SPEC", "SUPPLIER_SPEC", "BOQ"]} == {
        "BID_FORM": None, "REQUIREMENT_SPEC": FIX_LABEL, "TEST_SPEC": FIX_TYPE,
        "PURCHASE_SPEC": FIX_LABEL, "SUPPLIER_SPEC": None, "BOQ": None}
