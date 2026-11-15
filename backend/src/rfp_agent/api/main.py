import json
import logging
import sys
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import ResponseValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from rfp_agent.api import (
    assistant,
    businesses,
    evaluation,
    prompt_evals,
    prompts,
    reference,
    runs,
    suggestions,
)
from rfp_agent.config import get_settings
from rfp_agent.db.connection import connect
from rfp_agent.llm import trace
from rfp_agent.llm.client import ai_mode, ai_model
from rfp_agent.pipeline import ocr, run_queue

app = FastAPI(title="RFP 기술 검토 지원 API", version="0.2.0")
app.include_router(runs.router)
app.include_router(reference.router)
app.include_router(businesses.router)
app.include_router(evaluation.router)
app.include_router(suggestions.router)
app.include_router(assistant.router)
app.include_router(prompt_evals.router)
app.include_router(prompts.router)

log = logging.getLogger(__name__)


@app.exception_handler(ResponseValidationError)
def bad_response(request: Request, exc: ResponseValidationError) -> JSONResponse:
    """모양이 틀린 응답은 내보내지 않는다 (api-contract). 값은 로그에 남기지 않는다(원문 문장)."""
    fields = sorted({".".join(str(p) for p in e["loc"]) + f" ({e['type']})"
                     for e in exc.errors()})
    log.error("응답 모양이 맞지 않음: %s %s — %s", request.method, request.url.path,
              "; ".join(fields[:20]))
    return JSONResponse({"detail": "서버 응답이 정해진 모양과 맞지 않아 보내지 않았습니다."},
                        status_code=500)


class Health(BaseModel):
    status: str
    database: str
    schema_version: str | None
    llm_configured: bool
    # AI 사용 방식 (add-ai-mode): GEMINI · LOCAL · OFF. 키·사내 주소는 주지 않는다
    ai_mode: Literal["GEMINI", "LOCAL", "OFF"]
    ai_model: str | None
    external_send: bool
    # 스캔 PDF·그림 속 글자 읽기 (add-ocr): 엔진이 있고 켜져 있는지, 엔진 판
    ocr_available: bool = False
    ocr_engine: str | None = None
    # 검토 실행 대기열 (add-run-queue): 실행 방식(INLINE 웹 서버 안 / WORKER 처리기),
    # 살아 있는 처리기 수, 대기 작업 수
    run_mode: Literal["INLINE", "WORKER"] = "INLINE"
    workers_alive: int = 0
    jobs_queued: int = 0
    # AI 호출 기록 원문 저장 (add-ai-call-trace). 켜져 있으면 안내 문장
    trace_raw: bool = False
    trace_raw_warning: str | None = None
    # 프롬프트를 어디서 가져오나 (add-langfuse-prompts): CODE(코드 판) · LANGFUSE(그 표시의 판,
    # 문제가 있으면 역할마다 코드 판). 상태 점검은 Langfuse에 묻지 않는다(프롬프트 관리 화면이 묻음)
    prompt_source: Literal["CODE", "LANGFUSE"] = "CODE"
    prompt_label: str | None = None
    # 평가 결과를 Langfuse 실험으로 남기는가 (add-langfuse-experiments, RFP_LANGFUSE_RECORD)
    langfuse_record: bool = False


TRACE_RAW_WARNING = ("AI 호출 원문을 7일 동안 저장하고 있습니다. 고객 문서를 다루는 환경에서는 "
                     "RFP_TRACE_RAW를 끄세요.")


@app.get("/api/health", response_model=Health)
def health() -> Health:
    settings = get_settings()
    mode = ai_mode(settings)
    try:
        with connect() as conn:
            row = conn.execute(
                "SELECT max(version) FROM schema_migration"
            ).fetchone()
            queue = run_queue.status(conn)
            trace.purge(conn)                # 보관 기간이 지난 AI 호출 원문 (add-ai-call-trace)
        database, version = "ok", row[0] if row else None
    except Exception:  # noqa: BLE001 - 상태 점검은 어떤 DB 오류든 "down"으로 알린다
        database, version = "down", None
        queue = {"workers_alive": 0, "jobs_queued": 0}
    return Health(
        status="ok" if database == "ok" else "degraded",
        database=database,
        schema_version=version,
        llm_configured=mode != "OFF",
        ai_mode=mode,
        ai_model=ai_model(settings),
        external_send=mode == "GEMINI",
        ocr_available=ocr.available(),
        ocr_engine=ocr.engine_version() if ocr.available() else None,
        run_mode="WORKER" if settings.rfp_run_mode == "worker" else "INLINE",
        workers_alive=queue["workers_alive"], jobs_queued=queue["jobs_queued"],
        trace_raw=settings.rfp_trace_raw == "on",
        trace_raw_warning=TRACE_RAW_WARNING if settings.rfp_trace_raw == "on" else None,
        prompt_source="LANGFUSE" if settings.rfp_langfuse == "on" else "CODE",
        prompt_label=settings.rfp_langfuse_label if settings.rfp_langfuse == "on" else None,
        langfuse_record=settings.rfp_langfuse_record == "on",
    )


def dump_openapi() -> None:
    """`rfp-openapi`: 응답 스키마(/openapi.json)를 표준 출력으로 낸다. DB 없이 돈다."""
    json.dump(app.openapi(), sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
