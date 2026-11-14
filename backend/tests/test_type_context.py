"""AI 유형 판단의 문맥 (change update-type-context). 명세 requirement-extraction의 Scenario."""

import re

from rfp_agent.llm import tasks
from rfp_agent.pipeline.run import RunContext, create_run, execute_run
from tests.conftest import FakeLLM

VERSION = "test-dict-v1"


def type_lines(llm):
    return [line for p in llm.prompts if "유형 하나를 고른다" in p
            for line in re.findall(r"^\d+\. (.*)$", p, re.MULTILINE)]


def test_table_row_gets_table_and_section(db, spec):
    """Scenario: 표 행에 표 이름과 절 제목 — 묻는 글의 그 줄에 표 이름과 절이 들어간다."""
    llm = FakeLLM()
    run_id = create_run(db, VERSION, llm)
    assert execute_run(RunContext(db, VERSION, llm, None), run_id, [spec]) == "ENGINEER_REVIEW"
    lines = type_lines(llm)
    assert lines
    rows = [line for line in lines if "표 TS-" in line]
    assert rows and all(line.startswith("[") and "절 " in line.split("]")[0] for line in rows)


def test_line_without_context_is_text_only():
    """Scenario: 문맥이 없는 줄 — 문장만 들어간다."""
    llm = FakeLLM()
    out = tasks.type_unclassified(llm, ["The panel shall be grey.", "Rated current / A / 3150"],
                                  contexts=[None, "절 3 DATA SHEET · 표 TS-230-GIS · 구분 CB"])
    assert out == ["NONE", "NONE"]
    assert type_lines(llm) == [
        "The panel shall be grey.",
        "[절 3 DATA SHEET · 표 TS-230-GIS · 구분 CB] Rated current / A / 3150"]
