"""위험 표현 사전에 추가 제안 API (add-rule-suggestion, SCR-08-3·SCR-17).

뜻으로 찾은 후보(add-meaning-search): 사전 추가 후보, 항목 연결 후보.
"""

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from rfp_agent.api.auth import CurrentUser
from rfp_agent.api.schemas import MeaningCandidate, RiskMeaning, RuleEdit, RuleSuggestion
from rfp_agent.db.connection import connect
from rfp_agent.pipeline import meaning, review, rule_suggestion

router = APIRouter(prefix="/api", tags=["사전 추가 제안"])


class SuggestBody(BaseModel):
    expression: str = Field(max_length=200)
    note: str | None = Field(None, max_length=500)


class AcceptBody(BaseModel):
    value: dict[str, Any]                 # language, risk_kind, context_rule (표현은 제안 그대로)
    reason: str | None = None


class DeclineBody(BaseModel):
    reason: str | None = None


def _call(fn):
    with connect() as conn:
        try:
            return fn(conn)
        except review.ReviewError as exc:
            raise HTTPException(exc.status, str(exc)) from exc


@router.get("/runs/{run_id}/rule-suggestions")
def run_suggestions(run_id: int) -> list[RuleSuggestion]:
    return _call(lambda conn: rule_suggestion.listing(conn, run_id))


@router.post("/runs/{run_id}/rule-suggestions", status_code=201)
def suggest(run_id: int, body: SuggestBody, user: CurrentUser) -> RuleSuggestion:
    return _call(lambda conn: rule_suggestion.suggest(conn, run_id, body.expression, body.note,
                                                      user.user_id))


@router.get("/rule-suggestions")
def suggestions(status: Literal["PENDING", "ACCEPTED", "DECLINED"] | None = None
                ) -> list[RuleSuggestion]:
    return _call(lambda conn: rule_suggestion.listing(conn, status=status))


@router.post("/rule-suggestions/{suggestion_id}/accept")
def accept(suggestion_id: int, body: AcceptBody, user: CurrentUser) -> RuleSuggestion:
    return _call(lambda conn: rule_suggestion.accept(conn, suggestion_id, body.value, body.reason,
                                                     user.user_id))


@router.post("/rule-suggestions/{suggestion_id}/decline")
def decline(suggestion_id: int, body: DeclineBody, user: CurrentUser) -> RuleSuggestion:
    return _call(lambda conn: rule_suggestion.decline(conn, suggestion_id, body.reason,
                                                      user.user_id))


@router.get("/runs/{run_id}/meaning-candidates")
def risk_meaning(run_id: int) -> RiskMeaning:
    return _call(lambda conn: meaning.risk_candidates(conn, run_id))


@router.get("/item-candidates")
def item_candidates() -> list[MeaningCandidate]:
    return _call(meaning.item_candidates)


@router.post("/item-candidates/{candidate_id}/accept")
def accept_item(candidate_id: int, user: CurrentUser) -> RuleEdit:
    return _call(lambda conn: meaning.accept_item(conn, candidate_id, user.user_id))


@router.post("/item-candidates/{candidate_id}/hide", status_code=204)
def hide_item(candidate_id: int, user: CurrentUser) -> None:
    _call(lambda conn: meaning.hide_item(conn, candidate_id, user.user_id))
