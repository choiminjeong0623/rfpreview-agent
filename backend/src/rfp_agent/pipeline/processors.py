"""문서 종류별 처리기 (add-document-processors, C1).

처리기는 네 가지만 정한다: AI 문장 구분·유형 질문에 넣는 문서 종류 설명 한 줄, 처리 뒤 점검 기준,
점검에 걸렸을 때 다시 물을 AI 단계(update-partial-reprocess), 공통 추출 규칙에 더할 종류별 추출 규칙
(add-kind-extract-rules). 처리기는 판정·후보를 고르지 않는다(CR-01). 문장은 [제안].
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from rfp_agent.pipeline.extract import FORM_NOTES, MARK_TABLE_ROWS


@dataclass(frozen=True)
class Stats:
    """처리한 문서에서 저장할 줄 수 (점검 재료). 저장 전에 세어 저장 순서와 상관없다."""
    table_cells: int        # 표 칸 요구값 줄
    requirements: int       # 요구사항 줄
    tests: int              # 시험(TEST) 유형 요구사항 줄
    marks: int              # 공급사 C/D/E 표시가 있는 줄
    table_rows: int = 0     # 논리 표의 행 수 (물량표 점검, add-boq-processor)


# 점검: 줄 수 → 걸린 이유(통과면 None)
Check = Callable[[Stats], str | None]

# 점검에 걸리면 다시 물을 AI 단계. 표 칸·C/D/E 표시는 AI에 묻지 않아 다시 물어도 같으므로 없음
LABEL = "LABEL"     # 요구 문장이 하나도 남지 않은 절의 문장 구분
TYPE = "TYPE"       # 유형을 정하지 못한(NONE) 줄의 유형


def _no_table_cells(s: Stats) -> str | None:
    return None if s.table_cells else "입찰 서식인데 표 칸 요구값이 하나도 없습니다"


def _no_requirements(label: str) -> Check:
    def check(s: Stats) -> str | None:
        return None if s.requirements else f"{label}인데 요구사항 줄이 하나도 없습니다"
    return check


def _no_tests(s: Stats) -> str | None:
    return None if s.tests else "시험 사양서인데 시험 유형 줄이 하나도 없습니다"


def _no_marks(s: Stats) -> str | None:
    return None if s.marks else "공급사 사양서인데 C/D/E 준수 표시가 하나도 없습니다"


def _no_table_rows(s: Stats) -> str | None:
    return None if s.table_rows else "물량표인데 표 줄이 하나도 없습니다"


@dataclass(frozen=True)
class Processor:
    kind: str                   # 처리기 이름 = 문서 종류 (GENERAL은 일반)
    name: str                   # 사람이 읽는 이름
    hint: str | None            # AI 질문 첫머리에 넣는 문서 종류 설명
    check: Check | None         # 처리 뒤 점검 (없으면 점검하지 않음)
    fix: str | None = None      # 점검에 걸리면 다시 물을 AI 단계 (없으면 다시 묻지 않음)
    rules: frozenset[str] = field(default_factory=frozenset)   # 종류별 추출 규칙 (extract.py)


GENERAL = Processor("GENERAL", "일반", None, None)
PROCESSORS: dict[str, Processor] = {
    "BID_FORM": Processor(
        "BID_FORM", "입찰 서식",
        "입찰 서식(가격표·데이터시트 묶음). 표 칸의 요구값과 제출 서식을 채우는 안내 문장이 많다.",
        _no_table_cells, rules=frozenset({FORM_NOTES})),
    "REQUIREMENT_SPEC": Processor(
        "REQUIREMENT_SPEC", "요구 사양서",
        "기술 요구 사양서. 입찰자가 지켜야 할 shall·must 요구 문장이 많다.",
        _no_requirements("요구 사양서"), LABEL),
    "TEST_SPEC": Processor(
        "TEST_SPEC", "시험 사양서",
        "시험 사양서. 시험 항목·시험 입회·성적서 제출 요구가 많다.", _no_tests, TYPE),
    "PURCHASE_SPEC": Processor(
        "PURCHASE_SPEC", "구매 요청서",
        "구매 요청서. 공급 범위·수량·납기·상업 조건 문장이 많다.",
        _no_requirements("구매 요청서"), LABEL),
    "SUPPLIER_SPEC": Processor(
        "SUPPLIER_SPEC", "공급사 사양서",
        "공급사 사양서(답안). 조항마다 공급사의 C/D/E 준수 표시와 고객 의견이 있다.", _no_marks,
        rules=frozenset({MARK_TABLE_ROWS})),
    # 표 줄은 AI에 묻지 않아 다시 물어도 같으므로 다시 묻지 않는다
    "BOQ": Processor(
        "BOQ", "물량표",
        "물량표(BOQ). 품목·수량·단위 표가 대부분이고 기술 요구 문장은 적다.", _no_table_rows),
    "UNKNOWN": GENERAL,
}


def processor_for(doc_kind: str) -> Processor:
    """문서 종류로 처리기를 고른다 (코드 표, AI가 고르지 않음)."""
    return PROCESSORS.get(doc_kind, GENERAL)
