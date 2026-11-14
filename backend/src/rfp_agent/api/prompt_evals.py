"""프롬프트 평가 기록 조회 API (add-prompt-eval, FR-18). 읽기만 한다.

평가 실행은 명령 `rfp-db eval-prompts`로 한다(비용이 드는 일이라 화면에서 시작하지 않음).
"""

from fastapi import APIRouter, HTTPException

from rfp_agent.api.schemas import PromptEvalDetail, PromptEvalList
from rfp_agent.db.connection import connect
from rfp_agent.pipeline import prompt_eval

router = APIRouter(prefix="/api/prompt-evals", tags=["프롬프트 평가"])


@router.get("")
def evals(set: str | None = None) -> PromptEvalList:     # noqa: A002 - 주소 인자 이름 그대로
    with connect() as conn:
        rows = prompt_eval.runs(conn, set)
    return {"runs": rows, "latest_by_model": prompt_eval.latest_by_model(rows)}


@router.get("/{eval_id}")
def detail(eval_id: int) -> PromptEvalDetail:
    with connect() as conn:
        found = prompt_eval.runs(conn, eval_id=eval_id)
        if not found:
            raise HTTPException(404, f"평가 {eval_id}이(가) 없습니다.")
        return {"run": found[0], "items": prompt_eval.items_of(conn, eval_id)}
