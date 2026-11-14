"""사업 현황 API (add-project-status): 사업 목록·상세·만들기·고치기, 제출 완료 표시, 검토 연결.

사업 정보는 사람이 넣고 판정에 쓰지 않는다. 범위 상태는 연결된 검토에서 계산한다.
"""

from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from rfp_agent.api.schemas import BusinessDetail, BusinessList, BusinessLog, RunSummary
from rfp_agent.db.connection import connect
from rfp_agent.pipeline import business, queries, review

router = APIRouter(prefix="/api", tags=["사업 현황"])


class BusinessInfo(BaseModel):
    """사업 정보. 보낸 칸만 바꾸고 빈 문자열은 비우기로 본다. 사업명은 비울 수 없다."""
    business_name: str | None = Field(None, max_length=200)
    customer_name: str | None = Field(None, max_length=200)
    country: str | None = Field(None, max_length=60)
    tender_no: str | None = Field(None, max_length=80)
    order_mode: str | None = Field(None, max_length=200)
    due_date: date | str | None = None
    sales_id: int | None = None
    actor_id: int | None = None

    def info(self) -> dict:
        return self.model_dump(exclude_unset=True, exclude={"actor_id"})


class Actor(BaseModel):
    actor_id: int | None = None


class RunBusiness(BaseModel):
    business_id: int | None = None      # None이면 연결 해제
    actor_id: int | None = None


def _call(call):
    try:
        return call()
    except review.ReviewError as exc:
        raise HTTPException(exc.status, str(exc)) from exc


def _detail(business_id: int, user_id: int | None = None) -> dict:
    with connect() as conn:
        return _call(lambda: business.detail(conn, business_id, user_id))


@router.get("/businesses")
def businesses(user_id: int | None = None,
               scope: Literal["mine", "all"] = Query("all")) -> BusinessList:
    """사업 목록과 요약. scope=mine이면 user_id가 관여한 사업만 (내 사업)."""
    if scope == "mine" and user_id is None:
        raise HTTPException(400, "내 사업은 user_id가 필요합니다.")
    with connect() as conn:
        return business.business_list(conn, user_id, scope)


@router.post("/businesses", status_code=201)
def create_business(body: BusinessInfo) -> BusinessDetail:
    with connect() as conn:
        business_id = _call(lambda: business.create(conn, body.info(), body.actor_id))
    return _detail(business_id, body.actor_id)


@router.get("/businesses/{business_id}")
def business_detail(business_id: int, user_id: int | None = None) -> BusinessDetail:
    return _detail(business_id, user_id)


@router.put("/businesses/{business_id}")
def update_business(business_id: int, body: BusinessInfo) -> BusinessDetail:
    """사업 정보를 고친다. 바뀐 칸은 사업 이력에 남고, 사업명은 연결 검토에도 맞춘다."""
    with connect() as conn:
        _call(lambda: business.update(conn, business_id, body.info(), body.actor_id))
    return _detail(business_id, body.actor_id)


@router.post("/businesses/{business_id}/submitted")
def mark_submitted(business_id: int, body: Actor) -> BusinessDetail:
    """제출 완료 표시. 연결 검토가 모두 승인되어야 한다 (아니면 409)."""
    with connect() as conn:
        _call(lambda: business.set_submitted(conn, business_id, True, body.actor_id))
    return _detail(business_id, body.actor_id)


@router.delete("/businesses/{business_id}/submitted")
def unmark_submitted(business_id: int, actor_id: int | None = None) -> BusinessDetail:
    with connect() as conn:
        _call(lambda: business.set_submitted(conn, business_id, False, actor_id))
    return _detail(business_id, actor_id)


@router.get("/businesses/{business_id}/history")
def business_history(business_id: int) -> list[BusinessLog]:
    with connect() as conn:
        return _call(lambda: business.history(conn, business_id))


@router.put("/runs/{run_id}/business")
def link_run(run_id: int, body: RunBusiness) -> RunSummary:
    """검토를 사업에 연결하거나 해제한다. 검토 이력에 남고, FR-06 비교 범위는 바뀌지 않는다."""
    with connect() as conn:
        _call(lambda: business.link(conn, run_id, body.business_id, body.actor_id))
        return queries.run_summary(conn, run_id)
