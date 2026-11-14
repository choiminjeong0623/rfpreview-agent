"""기준 데이터 API (SCR-16 제품표, SCR-17 판정 규칙). 제품표는 읽기만, 규칙 사전은 고친다."""

from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel

from rfp_agent.api.schemas import (
    CompareRule,
    DocKindRule,
    ItemKey,
    PeakCheck,
    Product,
    ProductDetail,
    ProductFamily,
    RiskExpression,
    RuleDictionary,
    RuleEdit,
)
from rfp_agent.db.connection import connect
from rfp_agent.pipeline import engineering, product_export, reference, rule_edit

router = APIRouter(prefix="/api")


@router.get("/products")
def products(response: Response, family: str | None = None, q: str | None = None,
             offset: int = 0, limit: int = Query(100, le=500), cards: bool = True) -> list[Product]:
    """제품 목록: 제품군 거르기, 코드·이름 검색. 빈 칸 수·팀 가정·판정에 쓰인 수를 함께 낸다."""
    with connect() as conn:
        response.headers["X-Total-Count"] = str(reference.count_products(conn, family, q, cards))
        return reference.products(conn, family, q, offset, limit, cards)


@router.get("/products/families")
def product_families() -> list[ProductFamily]:
    """제품군 탭과 위 요약 칸."""
    with connect() as conn:
        return reference.families(conn)


XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


XLSX_FILE = {200: {"content": {XLSX_TYPE: {"schema": {"type": "string", "format": "binary"}}},
                   "description": "엑셀 파일"}}


@router.get("/products/export", response_class=Response, responses=XLSX_FILE)
def export_products(family: str | None = None, q: str | None = None,
                    cards: bool = True) -> Response:
    """제품표 엑셀 (SCR-16 내보내기). 목록과 같은 거르기. X-Row-Count = 제품 수."""
    with connect() as conn:
        name, body, n = product_export.products_xlsx(conn, family, q or None, cards)
    return Response(body, media_type=XLSX_TYPE, headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}",
        "X-Row-Count": str(n), "Access-Control-Expose-Headers": "X-Row-Count"})


@router.get("/products/{code}")
def product(code: str) -> ProductDetail:
    """제품 하나: 전체 칸, 판정에 쓰인 곳, 제안 포인트, 같은 제품군 현장 이력."""
    with connect() as conn:
        try:
            return reference.product(conn, code)
        except reference.NotFound as e:
            raise HTTPException(404, str(e)) from e


@router.get("/rules/compare")
def compare_rules() -> list[CompareRule]:
    with connect() as conn:
        return reference.compare_rules(conn)


@router.get("/rules/items")
def rule_items() -> list[ItemKey]:
    with connect() as conn:
        return reference.items(conn)


@router.get("/rules/risk-expressions")
def risk_expressions() -> list[RiskExpression]:
    with connect() as conn:
        return reference.risk_expressions(conn)


@router.get("/rules/doc-kinds")
def doc_kind_rules() -> list[DocKindRule]:
    """문서 종류 규칙 사전 (순서대로)."""
    with connect() as conn:
        return reference.doc_kind_rules(conn)


class RuleChange(BaseModel):
    """규칙 추가·수정. value 칸은 사전마다 다르다 (pipeline/rule_edit.py). 사유는 꼭 적는다."""
    value: dict[str, Any]
    reason: str | None = None
    actor_id: int | None = None


class RuleRemoval(BaseModel):
    reason: str | None = None
    actor_id: int | None = None


def _edit(call):
    """규칙 고침 오류(검사·권한·겹침)를 HTTP 응답으로 바꾼다."""
    try:
        with connect() as conn:
            return call(conn)
    except rule_edit.RuleEditError as exc:
        raise HTTPException(exc.status, str(exc)) from exc


@router.get("/rules/edits")
def rule_edits(dictionary: RuleDictionary | None = None) -> list[RuleEdit]:
    """규칙 고침 이력, 새것부터. 버린 고침도 함께 낸다."""
    return _edit(lambda conn: rule_edit.edits(conn, dictionary))


@router.post("/rules/{dictionary}", status_code=201)
def add_rule(dictionary: RuleDictionary, body: RuleChange) -> RuleEdit:
    """규칙 한 줄 추가 (엔지니어·승인자). 지운 같은 키 줄이 있으면 되살린다."""
    return _edit(lambda conn: rule_edit.add(conn, dictionary, body.value, body.reason,
                                            body.actor_id))


@router.put("/rules/{dictionary}/{row_id}")
def update_rule(dictionary: RuleDictionary, row_id: str, body: RuleChange) -> RuleEdit:
    return _edit(lambda conn: rule_edit.update(conn, dictionary, row_id, body.value,
                                               body.reason, body.actor_id))


@router.delete("/rules/{dictionary}/{row_id}")
def delete_rule(dictionary: RuleDictionary, row_id: str, body: RuleRemoval) -> RuleEdit:
    """규칙 한 줄 삭제. 지난 결과가 가리키는 사전은 끄고, 쓰이는 표준 항목은 막는다."""
    return _edit(lambda conn: rule_edit.delete(conn, dictionary, row_id, body.reason,
                                               body.actor_id))


@router.get("/engineering/peak-check")
def peak_check(ik_ka: float = Query(..., gt=0), frequency_hz: float = Query(..., gt=0),
               peak_ka: float = Query(..., gt=0)) -> PeakCheck:
    """검산 확인 (add-check-calculator): 판정 상세에서 값을 바꿔 보는 참고 계산. DB 안 씀."""
    return PeakCheck(**engineering.peak_check(ik_ka, frequency_hz, peak_ka))
