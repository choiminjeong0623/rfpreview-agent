"""정답지·채점 API (add-evaluation, SCR-19).

정답지 넣기는 명령 `rfp-db load-answer-key`·`make-answer-key`로 한다.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from rfp_agent.api.schemas import AnswerKey, EvalRun, EvalScore
from rfp_agent.db.connection import connect
from rfp_agent.pipeline import evaluation, review

router = APIRouter(prefix="/api/eval", tags=["정답지·채점"])


class ScoreRequest(BaseModel):
    run_ids: list[int] = Field(min_length=1)
    key_id: int | None = None                         # 유형 정답지
    req_key_id: int | None = None                     # 요구사항 정답지 (K1·K2·K3·K10)
    note: str | None = Field(None, max_length=500)    # 무엇을 고쳤나
    actor_id: int | None = None


@router.get("/keys")
def keys() -> list[AnswerKey]:
    with connect() as conn:
        return evaluation.keys(conn)


@router.get("/runs")
def runs() -> list[EvalRun]:
    with connect() as conn:
        return evaluation.candidate_runs(conn)


@router.get("/scores")
def scores() -> list[EvalScore]:
    with connect() as conn:
        return evaluation.history(conn)


@router.post("/scores")
def score(body: ScoreRequest) -> EvalScore:
    with connect() as conn:
        try:
            return evaluation.score(conn, body.run_ids, body.key_id, body.note, body.actor_id,
                                    body.req_key_id)
        except review.ReviewError as exc:
            raise HTTPException(exc.status, str(exc)) from exc
