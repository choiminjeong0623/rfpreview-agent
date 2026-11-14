"""FR-02 구조 나누기와 FR-03 추출을 합성 docx로 본다.

명세 document-intake, requirement-extraction의 Scenario.
"""

import pytest

from rfp_agent.pipeline.docx_reader import Block, read_blocks
from rfp_agent.pipeline.extract import extract
from rfp_agent.pipeline.structure import build_tables, find_sections, heading_of
from tests.docx_factory import build_gis_spec

ROLES = {"No.": "ITEM_NO", "Description": "ITEM_NAME", "Unit": "UNIT",
         "Employer's Requirement": "REQUIRED", "Warranted Data": "WARRANTED"}


@pytest.fixture(scope="module")
def doc(tmp_path_factory):
    blocks = read_blocks(build_gis_spec(tmp_path_factory.mktemp("docx") / "spec.docx"))
    sections = find_sections(blocks)
    tables = build_tables(blocks, ROLES)
    return blocks, sections, tables


def test_find_sections_assigns_last_section_to_document_end():
    blocks = [
        Block(seq=0, kind="P", text="1. 일반사항", line_no=1, line_count=1),
        Block(seq=1, kind="P", text="본문", line_no=2, line_count=1),
        Block(seq=2, kind="P", text="2. 요구사항", line_no=3, line_count=1),
        Block(seq=3, kind="P", text="마지막 본문", line_no=4, line_count=1),
    ]

    sections = find_sections(blocks)

    assert [section.line_end for section in sections] == [2, 4]


def test_heading_patterns():
    assert heading_of("5.2.2 154 kV 가스절연개폐장치")[:2] == ("NUM2", "5.2.2")
    assert heading_of("1)주 모 선")[:2] == ("PAREN_NUM", "1")
    assert heading_of("가. 일반사항")[:2] == ("HANGUL", "가")
    assert heading_of("표. 주모선 설계 자료") is None
    assert heading_of("3)기기 조작함에는 수동스위치를 설치하여야 한다. (투입, 트립") is None


def test_toc_lines_are_not_body_sections(doc):
    _, sections, _ = doc
    clar = [s for s in sections if s.title.startswith("CLARIFICATION")]
    assert [s.is_toc for s in clar] == [True, False]


def test_heading_followed_by_body_in_same_paragraph(doc):
    blocks, sections, tables = doc
    deemed = [c for c in extract(blocks, sections, tables) if "deemed" in c.text]
    assert len(deemed) == 1
    assert deemed[0].section.title.startswith("CLARIFICATION")
    assert deemed[0].text.startswith("Any item")


def test_split_table_is_joined_without_repeated_header(doc):
    _, _, tables = doc
    [table] = [t for t in tables if t.name == "TS-154-GIS"]
    assert table.source_table_nos == [0, 1]
    numbers = [r.item_no for r in table.rows]
    assert numbers == ["1", "2", "3", "4", "5", "5-1", "5-2", "6", "7"]
    assert not any(r.item_name == "Description" for r in table.rows)
    assert table.rows[5].parent_index == 4


def test_writing_rule_is_not_a_requirement(doc):
    blocks, sections, tables = doc
    rule = [c for c in extract(blocks, sections, tables) if "bidder shall indicate" in c.text]
    assert rule[0].req_kind == "WRITING_RULE"


def _row(seq, table_no, row_no, cells):
    return Block(seq=seq, kind="R", text=" | ".join(cells), line_no=seq + 1, line_count=1,
                 table_no=table_no, row_no=row_no, cells=cells, raw_cells=cells)


def test_table_name_from_caption_paragraph_right_before_table():
    """Scenario: 표 바로 앞 단락의 표 이름 —
    표 안에 제목 줄이 없으면 바로 앞 단락 "TS-… — 설명"을 표 이름으로 쓴다."""
    head = ["No.", "Description", "Unit", "Employer's Requirement"]
    blocks = [
        Block(seq=0, kind="P", text="TS-170-GIS — Added deviation-candidate requirements",
              line_no=1, line_count=1),
        _row(1, 0, 0, head),
        _row(2, 0, 1, ["D-01", "Rated voltage", "kV", "≥180 kV"]),
        Block(seq=3, kind="P", text="Refer to TS-245-GIS for the other bay.",
              line_no=4, line_count=1),
        _row(4, 1, 0, head),
        _row(5, 1, 1, ["1", "Rated voltage", "kV", "≥245 kV"]),
    ]

    tables = build_tables(blocks, ROLES)

    assert [t.name for t in tables] == ["TS-170-GIS", None]
