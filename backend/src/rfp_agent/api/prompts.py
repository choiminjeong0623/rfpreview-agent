"""프롬프트 관리 API (add-prompt-view 조회, add-prompt-editor 고치기).

고치기는 Langfuse가 연결되어 있을 때만: 저장은 staging 새 버전, 운영 표시는 평가를 통과해야 옮긴다.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from rfp_agent.api.auth import CurrentUser
from rfp_agent.api.schemas import PromptDetail, PromptEvalJob, PromptOverview, PromptSaved
from rfp_agent.db.connection import connect
from rfp_agent.pipeline import prompt_editor, prompt_registry

router = APIRouter(prefix="/api/prompts", tags=["프롬프트 관리"])


class DraftIn(BaseModel):
    text: str = Field(min_length=1, max_length=20000)
    message: str | None = None


class PromoteIn(BaseModel):
    job_id: int


def _run(fn):
    try:
        return fn()
    except prompt_editor.EditorError as exc:
        raise HTTPException(exc.status, exc.message) from exc


@router.get("")
def prompts() -> PromptOverview:
    with connect() as conn:
        return prompt_registry.overview(conn)


@router.get("/{role}")
def prompt_detail(role: str) -> PromptDetail:
    return _run(lambda: prompt_editor.detail(role))


@router.post("/{role}/drafts")
def save_draft(role: str, body: DraftIn, user: CurrentUser) -> PromptSaved:
    with connect() as conn:
        return _run(lambda: prompt_editor.save_draft(conn, role, user.user_id, body.text,
                                                     body.message))


@router.post("/{role}/evaluations")
def start_evaluation(role: str, user: CurrentUser) -> PromptEvalJob:
    with connect() as conn:
        return _run(lambda: prompt_editor.start_eval(conn, role, user.user_id))


@router.get("/{role}/evaluations/latest")
def latest_evaluation(role: str) -> PromptEvalJob | None:
    return prompt_editor.latest_job(role)


@router.post("/{role}/promote")
def promote(role: str, body: PromoteIn, user: CurrentUser) -> PromptSaved:
    with connect() as conn:
        return _run(lambda: prompt_editor.promote(conn, role, user.user_id, body.job_id))
