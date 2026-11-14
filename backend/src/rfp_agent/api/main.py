import json
import logging
import sys
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import ResponseValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from rfp_agent.api import assistant, businesses, evaluation, reference, runs, suggestions
from rfp_agent.config import get_settings
from rfp_agent.db.connection import connect
from rfp_agent.llm.client import ai_mode, ai_model
from rfp_agent.pipeline import ocr

app = FastAPI(title="RFP 기술 검토 지원 API", version="0.2.0")
app.include_router(runs.router)
app.include_router(reference.router)
app.include_router(businesses.router)
app.include_router(evaluation.router)
app.include_router(suggestions.router)
app.include_router(assistant.router)

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


@app.get("/api/health", response_model=Health)
def health() -> Health:
    settings = get_settings()
    mode = ai_mode(settings)
    try:
        with connect() as conn:
            row = conn.execute(
                "SELECT max(version) FROM schema_migration"
            ).fetchone()
        database, version = "ok", row[0] if row else None
    except Exception:  # noqa: BLE001 - 상태 점검은 어떤 DB 오류든 "down"으로 알린다
        database, version = "down", None
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
    )


def dump_openapi() -> None:
    """`rfp-openapi`: 응답 스키마(/openapi.json)를 표준 출력으로 낸다. DB 없이 돈다."""
    json.dump(app.openapi(), sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
