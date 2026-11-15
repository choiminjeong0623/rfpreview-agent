"""프롬프트 관리 조회 API (add-prompt-view). 읽기만 한다. 프롬프트 글은 코드에서만 고친다."""

from fastapi import APIRouter

from rfp_agent.api.schemas import PromptOverview
from rfp_agent.db.connection import connect
from rfp_agent.pipeline import prompt_registry

router = APIRouter(prefix="/api/prompts", tags=["프롬프트 관리"])


@router.get("")
def prompts() -> PromptOverview:
    with connect() as conn:
        return prompt_registry.overview(conn)
