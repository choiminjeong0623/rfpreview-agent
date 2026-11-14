"""검토 도우미 API (add-review-assistant, FR-17). 읽기만 한다."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from rfp_agent.api.schemas import AssistantAnswer
from rfp_agent.db.connection import connect
from rfp_agent.pipeline import ai_usage, assistant, review
from rfp_agent.pipeline.service import make_context

router = APIRouter(prefix="/api", tags=["검토 도우미"])


class AskBody(BaseModel):
    question: str = Field(max_length=500)


@router.post("/runs/{run_id}/assistant")
def ask(run_id: int, body: AskBody) -> AssistantAnswer:
    with connect() as conn:
        try:
            llm = make_context(conn).llm
            with ai_usage.tracked(conn, "ASSISTANT", run_id, llm):
                return assistant.ask(conn, run_id, body.question, llm)
        except review.ReviewError as exc:
            raise HTTPException(exc.status, str(exc)) from exc
