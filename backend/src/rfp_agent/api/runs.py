"""검토 실행 API: 문서를 올려 실행을 시작하고, 상태와 결과(요구사항·값·위험 조건·판정·보증값·
손실 환산·일탈·질의 목록·제안 포인트)를 본다. 비교 제품 바꾸기, 손실값 고치기,
확인·승인(FR-10)도 여기서 한다."""

import hashlib
import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Form, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from rfp_agent.api.schemas import (
    ActionResult,
    AiUsage,
    ApprovalScreen,
    Assignment,
    AssignmentStatus,
    BulkResult,
    CompareTargets,
    CostSummary,
    Datasheet,
    DatasheetInfo,
    DecisionResult,
    Deliverables,
    DocKind,
    DocumentLines,
    DocumentPair,
    DocumentPreview,
    EngineeringCheck,
    Equipment,
    HandoffResult,
    Judgment,
    JudgmentCounts,
    LogEntry,
    Loss,
    LossResult,
    MyTasks,
    OutputItem,
    PastCompare,
    ProductSwitch,
    Proposal,
    ReadCheck,
    Requirement,
    Risk,
    RunDocument,
    RunFlow,
    RunListItem,
    RunLogItem,
    RunSummary,
    SalesHandoff,
    ScreenSummary,
    SendResult,
    StageResult,
    SubmissionCheck,
    SubmitResult,
    Tbe,
    TypeEditResult,
    User,
    Warranty,
)
from rfp_agent.config import get_settings
from rfp_agent.db.connection import connect
from rfp_agent.llm.client import make_llm
from rfp_agent.pipeline import (
    ai_usage,
    assignment_export,
    business,
    datasheet,
    doc_add,
    graph_flow,
    past_compare,
    preview,
    queries,
    read_checks,
    review,
    review_info,
    run_control,
    run_log,
    sales_handoff,
    source_lines,
    tbe,
)
from rfp_agent.pipeline.assignments import build_assignments
from rfp_agent.pipeline.cost_conditions import cost_summary
from rfp_agent.pipeline.export import outputs_docx
from rfp_agent.pipeline.handoff_mail import send_requests
from rfp_agent.pipeline.loss import recalculate
from rfp_agent.pipeline.outputs import check_submission
from rfp_agent.pipeline.proposals import build_proposals
from rfp_agent.pipeline.reader import SUFFIXES
from rfp_agent.pipeline.run import switch_product
from rfp_agent.pipeline.screen_summary import home_summary, review_summary
from rfp_agent.pipeline.service import make_context, run_to_end, start_run

router = APIRouter(prefix="/api", tags=["검토 실행"])
DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
ZIP_TYPE = "application/zip"


def _file(media_type: str) -> dict:
    """내려받기 API의 성공 응답은 JSON이 아니라 파일이다 (/openapi.json에 밝힘)."""
    return {200: {"content": {media_type: {"schema": {"type": "string", "format": "binary"}}},
                  "description": "파일"}}


class ReviewInfo(BaseModel):
    """검토 정보. 보낸 칸만 바꾸고 빈 문자열은 비우기로 본다 (add-review-info)."""
    project_name: str | None = Field(None, max_length=200)
    review_name: str | None = Field(None, max_length=200)
    customer_name: str | None = Field(None, max_length=200)
    country: str | None = Field(None, max_length=60)
    due_date: date | str | None = None
    engineer_id: int | None = None
    actor_id: int | None = None

    def info(self) -> dict:
        return self.model_dump(exclude_unset=True,
                               exclude={"actor_id", "files", "choices", "business_id",
                                        "new_business_name"})


class DocumentChoice(BaseModel):
    """등록 화면에서 사람이 정한 문서 분류. 비운 칸은 규칙 결과를 쓴다."""
    bundle: Literal["A", "B", "C", "D"] | None = None
    doc_kind: DocKind | None = None


Choices = dict[str, DocumentChoice]          # 파일 이름 → 사람이 정한 분류


class LibraryFiles(BaseModel):
    files: list[str]


class LibraryRun(ReviewInfo):
    files: list[str]
    choices: Choices = {}
    business_id: int | None = None          # 진행 중인 사업에 추가 (add-project-status)
    new_business_name: str | None = Field(None, max_length=200)   # 새 사업 만들기


class ProductChoice(BaseModel):
    product_code: str | None = None       # None이면 자동 선택으로 되돌린다


class LossValues(BaseModel):
    loss_noload_kw: float | None = Field(None, ge=0)
    loss_load_kw: float | None = Field(None, ge=0)
    loss_aux_kw: float | None = Field(None, ge=0)


class Action(BaseModel):
    target: str     # judgment, warranty_candidate, output_item, proposal_point, risk_flag
    target_id: int
    action: str                     # CONFIRM, EDIT, REJECT, ADOPT, DISCARD
    value: dict | None = None       # EDIT: {"result"} / {"value", "unit"} / {"text"}
    reason: str | None = None
    actor_id: int | None = None


class TypeEdit(BaseModel):
    type_code: str                  # 유형 코드 또는 NONE(미분류)
    reason: str | None = None
    actor_id: int | None = None


class BulkAction(BaseModel):
    target: str = "judgment"
    ids: list[int]
    action: str = "CONFIRM"
    actor_id: int | None = None


class Actor(BaseModel):
    actor_id: int | None = None


class Rewind(BaseModel):
    """단계부터 다시 처리 (add-step-rewind): 처리 단계 이름과 사유."""
    step: str
    reason: str
    actor_id: int | None = None


class TaskStatus(BaseModel):
    status: str = Field(pattern="^(TODO|DOING|DONE)$")
    actor_id: int
    reply_note: str | None = None


class HandoffRequest(BaseModel):
    actor_id: int | None = None
    table_id: int | None = None      # 데이터시트일 때


class SendRequests(BaseModel):
    assignment_ids: list[int]
    actor_id: int | None = None
    resend: bool = False             # 메일 보냄(회신 대기) 요청 재요청 (update-todo-search)


class ExportAssignments(BaseModel):
    role: str | None = Field(None, pattern="^(COST|QUALITY|SALES)$")
    assignment_ids: list[int]


class Submit(BaseModel):
    actor_id: int | None = None
    approver_id: int | None = None
    comment: str | None = None


class Decision(BaseModel):
    decision: str = Field(pattern="^(APPROVED|REJECTED)$")
    comment: str | None = None
    actor_id: int | None = None


@contextmanager
def _ai(conn, feature: str, run_id: int) -> Iterator:
    """분석 밖 요청의 실행 문맥. AI를 불렀으면 사용량을 남긴다 (add-ai-usage-log)."""
    ctx = make_context(conn)
    with ai_usage.tracked(conn, feature, run_id, ctx.llm):
        yield ctx


def _review(call):
    """확인·승인 동작의 오류를 HTTP 응답으로 바꾼다."""
    try:
        return call()
    except review.ReviewError as exc:
        raise HTTPException(exc.status, str(exc)) from exc


def _summary(run_id: int) -> dict:
    with connect() as conn:
        summary = queries.run_summary(conn, run_id)
    if summary is None:
        raise HTTPException(404, f"검토 실행 {run_id}이(가) 없습니다.")
    return summary


NO_JUDGE_TARGET = ("판정 대상 문서(묶음 A·B)가 없어 검토를 시작하지 않았습니다. "
                   "묶음을 바꾸거나 판정할 문서를 더 올려 주세요.")


def _start(paths: list[Path], background: BackgroundTasks, info: dict,
           actor_id: int | None, choices: Choices | None = None,
           business_id: int | None = None, new_business_name: str | None = None) -> dict:
    bundles = {name: c.bundle for name, c in (choices or {}).items() if c.bundle}
    with connect() as conn:
        # 판정할 문서가 없으면 10분 분석해도 판정이 0건이라 실행을 만들기 전에 거절한다 (CR-09)
        if not preview.has_judge_target(conn, paths, bundles):
            raise HTTPException(400, NO_JUDGE_TARGET)
        # 검토 정보·사업 칸이 틀리면 실행을 만들기 전에 막는다
        _review(lambda: review_info.clean(info))
        _review(lambda: review_info.require_due(info))
        _review(lambda: review_info.check_engineer(conn, info.get("engineer_id") or None))
        _review(lambda: business.check_start(conn, business_id, new_business_name))
        run_id = start_run(conn, actor_id)
        _review(lambda: review_info.save_on_start(conn, run_id, info, actor_id))
        _review(lambda: business.link_on_start(conn, run_id, business_id, new_business_name,
                                               review_info.clean(info), actor_id))
    chosen = {name: c.model_dump(exclude_none=True) for name, c in (choices or {}).items()}
    background.add_task(run_to_end, run_id, paths, chosen)
    return _summary(run_id)


def _safe_name(name: str) -> str:
    name = Path(name).name
    if not name.lower().endswith(SUFFIXES) or re.search(r"[\x00/\\]", name):
        raise HTTPException(400, f"docx·PDF 파일만 받습니다: {name}")
    return name


@router.get("/users")
def users() -> list[User]:
    """로그인(범위 밖) 전까지 화면에서 고르는 사용자 목록."""
    with connect() as conn:
        return queries.users(conn)


@router.get("/runs")
def runs(limit: int = Query(50, le=200)) -> list[RunListItem]:
    with connect() as conn:
        return queries.run_list(conn, limit)


@router.get("/run-log")
def get_run_log(limit: int = Query(200, le=500)) -> list[RunLogItem]:
    """실행 기록: 검토마다 걸린 시간·단계별 시간·AI 사용량·추정 비용 (add-run-log)."""
    with connect() as conn:
        return run_log.run_log(conn, limit)


@router.get("/ai-usage")
def get_ai_usage(days: int = Query(30, ge=1, le=366)) -> AiUsage:
    """최근 days일의 날짜·기능별 AI 사용량과 추정 비용. 분석 실행 포함 (add-ai-usage-log)."""
    with connect() as conn:
        return ai_usage.summary(conn, days)


@router.get("/runs/{run_id}/flow")
def run_flow(run_id: int) -> RunFlow:
    """흐름 기록: 단계마다 걸린 시간·바뀐 건수·사람 동작·멈춘 자리 (add-flow-history, 읽기 전용)."""
    _summary(run_id)
    with connect() as conn:
        return graph_flow.history(conn, run_id)


@router.get("/requirements/{requirement_id}")
def requirement(requirement_id: int, run_id: int | None = None) -> Requirement:
    """요구사항 원문. run_id를 주면 그 실행의 문서 위치만 낸다."""
    with connect() as conn:
        item = queries.requirement(conn, requirement_id, run_id)
    if item is None:
        raise HTTPException(404, f"요구사항 {requirement_id}이(가) 없습니다.")
    return item


@router.get("/library")
def library() -> list[str]:
    """서버에 미리 둔 RFP 원문(data/private/rfp_docx) 목록."""
    docx_dir = get_settings().docx_dir
    if not docx_dir.exists():
        return []
    return sorted(p.name for p in docx_dir.iterdir() if p.suffix.lower() in SUFFIXES)


def _library_paths(files: list[str]) -> list[Path]:
    docx_dir = get_settings().docx_dir
    paths = [docx_dir / _safe_name(name) for name in files]
    missing = [p.name for p in paths if not p.exists()]
    if not paths or missing:
        raise HTTPException(400, f"없는 파일: {', '.join(missing) or '(파일 없음)'}")
    return paths


async def _save_uploads(files: list[UploadFile]) -> list[Path]:
    """올린 파일을 내용 해시 폴더에 둔다. 같은 파일이면 한 번만 저장한다."""
    upload_dir = get_settings().upload_dir
    paths = []
    for f in files:
        name = _safe_name(f.filename or "")
        data = await f.read()
        target = upload_dir / hashlib.sha256(data).hexdigest()[:16] / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(data)
        paths.append(target)
    if not paths:
        raise HTTPException(400, "파일이 없습니다.")
    return paths


def _preview(paths: list[Path]) -> list[dict]:
    with connect() as conn:
        try:
            return preview.preview(conn, paths)
        except preview.UnreadableFile as exc:
            raise HTTPException(400, f"문서를 열 수 없습니다: {exc}") from exc


@router.post("/runs/library/preview")
def library_preview(body: LibraryFiles) -> list[DocumentPreview]:
    """서버에 둔 RFP의 분석 전 분류 추천. 규칙만 쓰고 저장하지 않는다."""
    return _preview(_library_paths(body.files))


@router.post("/runs/preview")
async def upload_preview(files: list[UploadFile]) -> list[DocumentPreview]:
    """올린 docx의 분석 전 분류 추천. 규칙만 쓰고 DB에 저장하지 않는다."""
    return _preview(await _save_uploads(files))


@router.post("/runs/library", status_code=202)
def run_library(body: LibraryRun, background: BackgroundTasks) -> RunSummary:
    return _start(_library_paths(body.files), background, body.info(), body.actor_id, body.choices,
                  body.business_id, body.new_business_name)


@router.post("/runs", status_code=202)
async def run_upload(files: list[UploadFile], background: BackgroundTasks,
                     project_name: str | None = Form(None), review_name: str | None = Form(None),
                     customer_name: str | None = Form(None), country: str | None = Form(None),
                     due_date: str | None = Form(None), engineer_id: int | None = Form(None),
                     actor_id: int | None = Form(None),
                     choices: str | None = Form(None),
                     business_id: int | None = Form(None),
                     new_business_name: str | None = Form(None)) -> RunSummary:
    """올린 docx로 검토를 시작한다. 검토 정보 칸은 모두 고를 수 있다.

    파일은 내용 해시 폴더에 저장해 같은 파일이면 다시 처리하지 않는다.
    choices는 등록 화면에서 사람이 정한 분류 JSON ({파일 이름: {bundle, doc_kind}}).
    business_id(진행 중인 사업에 추가)나 new_business_name(새 사업 만들기)으로 사업에 잇는다.
    """
    try:
        chosen = TypeAdapter(Choices).validate_json(choices) if choices else {}
    except ValidationError as exc:
        raise HTTPException(400, f"문서 분류 값이 틀렸습니다: {exc.errors()[0]['msg']}") from exc
    paths = await _save_uploads(files)
    sent = {"project_name": project_name, "review_name": review_name,
            "customer_name": customer_name, "country": country, "due_date": due_date,
            "engineer_id": engineer_id}
    return _start(paths, background, {k: v for k, v in sent.items() if v is not None}, actor_id,
                  chosen, business_id, new_business_name)


@router.get("/runs/{run_id}")
def run_status(run_id: int) -> RunSummary:
    return _summary(run_id)


@router.put("/runs/{run_id}/info")
def update_info(run_id: int, body: ReviewInfo) -> RunSummary:
    """검토 정보를 고친다. 단계와 관계없이 고칠 수 있고 바뀐 칸은 이력에 남는다."""
    _summary(run_id)
    with connect() as conn:
        _review(lambda: review_info.update(conn, run_id, body.info(), body.actor_id))
    return _summary(run_id)


@router.get("/runs/{run_id}/documents")
def run_documents(run_id: int) -> list[RunDocument]:
    _summary(run_id)
    with connect() as conn:
        return queries.run_documents(conn, run_id)


@router.get("/runs/{run_id}/documents/{file_no}/lines")
def document_lines(run_id: int, file_no: int, from_: int = Query(alias="from"),
                   to: int = Query()) -> DocumentLines:
    """원문 줄 범위 (최대 40줄). 분석 때와 같은 줄 번호 (판정 상세 화면, add-judgment-view)."""
    _summary(run_id)
    settings = get_settings()
    txt_dir = settings.txt_dir if settings.txt_dir.exists() else None
    with connect() as conn:
        try:
            out = source_lines.document_lines(conn, run_id, file_no, from_, to, txt_dir)
        except source_lines.LineRangeError as exc:
            raise HTTPException(400, str(exc)) from exc
    if out is None:
        raise HTTPException(404, f"이 검토에 파일 {file_no} 문서가 없습니다.")
    return out


@router.get("/runs/{run_id}/pairs")
def run_pairs(run_id: int) -> list[DocumentPair]:
    _summary(run_id)
    with connect() as conn:
        return queries.run_pairs(conn, run_id)


@router.get("/runs/{run_id}/requirements")
def run_requirements(run_id: int, response: Response, document_id: int | None = None,
                     type_code: str | None = None, limit: int = Query(100, le=500),
                     offset: int = 0) -> list[Requirement]:
    _summary(run_id)
    with connect() as conn:
        response.headers["X-Total-Count"] = str(queries.count_requirements(
            conn, run_id, document_id=document_id, type_code=type_code))
        return queries.run_requirements(conn, run_id, document_id=document_id,
                                        type_code=type_code, limit=limit, offset=offset)


@router.get("/runs/{run_id}/risks")
def run_risks(run_id: int) -> list[Risk]:
    _summary(run_id)
    with connect() as conn:
        return queries.run_risks(conn, run_id)


@router.get("/runs/{run_id}/judgments")
def run_judgments(run_id: int, response: Response, result: str | None = None,
                  group: str | None = None, type_code: str | None = None,
                  q: str | None = None, unconfirmed: bool = False,
                  past: str | None = Query(None, pattern="^differs$"),
                  order: str | None = Query(None, pattern="^priority$"),
                  revised: bool = False,
                  limit: int = Query(100, le=500), offset: int = 0) -> list[Judgment]:
    """판정 목록. order=priority면 일탈 → 질의 → 확인 필요 → 작성 필요 → 준수 순서.
    past=differs면 지난 사람 판정과 다른 줄만 (add-review-memory).
    revised면 마지막 문서 추가 개정에서 바뀌거나 추가된 줄만 (add-revision-notice)."""
    _summary(run_id)
    filters = {"result": result, "group": group, "type_code": type_code, "q": q,
               "unconfirmed": unconfirmed, "past": past, "revised": revised}
    with connect() as conn:
        response.headers["X-Total-Count"] = str(queries.count_judgments(conn, run_id, **filters))
        return queries.run_judgments(conn, run_id, **filters, priority=order == "priority",
                                     limit=limit, offset=offset)


@router.get("/runs/{run_id}/summary")
def run_summary_text(run_id: int) -> ScreenSummary:
    """검토 상세 요약 상자 문장 (add-screen-summary). 코드가 틀에 채운다, AI 없음."""
    with connect() as conn:
        out = review_summary(conn, run_id)
    if out is None:
        raise HTTPException(404, f"검토 실행 {run_id}이(가) 없습니다.")
    return out


@router.get("/home/summary")
def home_summary_text(user_id: int | None = None) -> ScreenSummary:
    """홈 요약 상자 문장 (add-screen-summary). 내 차례 수는 홈 "내가 처리할 건"과 같다."""
    with connect() as conn:
        return home_summary(conn, user_id)


@router.get("/runs/{run_id}/judgment-counts")
def judgment_counts(run_id: int) -> JudgmentCounts:
    """판정 칩 건수 (판정 값마다, 확정 안 한 수, 그중 준수)."""
    _summary(run_id)
    with connect() as conn:
        return queries.judgment_counts(conn, run_id)


@router.get("/runs/{run_id}/equipment")
def run_equipment(run_id: int) -> list[Equipment]:
    _summary(run_id)
    with connect() as conn:
        return queries.run_equipment(conn, run_id)


@router.put("/runs/{run_id}/equipment/{group:path}/product")
def choose_product(run_id: int, group: str, body: ProductChoice) -> ProductSwitch:
    """설비 묶음의 비교 제품을 바꾸고 그 묶음을 다시 판정한다.

    이전 판정은 지우지 않고 현재가 아님으로 남긴다.
    """
    _summary(run_id)
    with connect() as conn:
        if conn.execute("SELECT 1 FROM judgment WHERE run_id = %s AND equipment_group = %s "
                        "LIMIT 1", (run_id, group)).fetchone() is None:
            raise HTTPException(404, f"설비 묶음 {group}이(가) 없습니다.")
        _review(lambda: review.require_stage(conn, run_id, "ENGINEER_REVIEW"))
        before = conn.execute("SELECT product_code FROM run_product_choice WHERE run_id = %s "
                              "AND equipment_group = %s", (run_id, group)).fetchone()
        try:
            with _ai(conn, "PRODUCT_SWITCH", run_id) as ctx:
                counts = switch_product(ctx, run_id, group, body.product_code)
        except KeyError as exc:
            raise HTTPException(400, f"없는 제품: {body.product_code}") from exc
        review.log(conn, run_id, "run_product_choice", run_id, "EDIT",
                   {"group": group, "product_code": before[0] if before else None},
                   {"group": group, "product_code": body.product_code}, "비교 제품 바꿔 보기",
                   review.default_user(conn, "ENGINEER"))
        conn.commit()
        return counts


@router.get("/runs/{run_id}/warranty")
def run_warranty(run_id: int, response: Response, status: str | None = None,
                 limit: int = Query(100, le=500), offset: int = 0) -> list[Warranty]:
    _summary(run_id)
    with connect() as conn:
        response.headers["X-Total-Count"] = str(queries.count_warranty(conn, run_id,
                                                                      status=status))
        return queries.run_warranty(conn, run_id, status=status, limit=limit, offset=offset)


@router.get("/runs/{run_id}/losses")
def run_losses(run_id: int) -> list[Loss]:
    _summary(run_id)
    with connect() as conn:
        return queries.run_losses(conn, run_id)


@router.put("/runs/{run_id}/losses/{loss_calc_id}")
def update_loss(run_id: int, loss_calc_id: int, body: LossValues) -> LossResult:
    """엔지니어가 손실값을 넣으면 다시 계산한다. 직접 넣은 값은 팀 가정으로 표시된다."""
    _summary(run_id)
    with connect() as conn:
        if conn.execute("SELECT 1 FROM loss_calc WHERE run_id = %s AND loss_calc_id = %s",
                        (run_id, loss_calc_id)).fetchone() is None:
            raise HTTPException(404, f"손실 환산 {loss_calc_id}이(가) 없습니다.")
        _review(lambda: review.require_stage(conn, run_id, "ENGINEER_REVIEW"))
        before = review.row(conn, "loss_calc", loss_calc_id, run_id)
        result = recalculate(conn, loss_calc_id, body.loss_noload_kw, body.loss_load_kw,
                             body.loss_aux_kw)
        review.log(conn, run_id, "loss_calc", loss_calc_id, "EDIT", before,
                   review.row(conn, "loss_calc", loss_calc_id, run_id), "손실값 고치기",
                   review.default_user(conn, "ENGINEER"))
        with _ai(conn, "LOSS_EDIT", run_id) as ctx:
            build_proposals(conn, run_id, ctx.llm)
        build_assignments(conn, run_id)
        conn.commit()
        return result


@router.get("/runs/{run_id}/cost-conditions")
def run_cost_conditions(run_id: int) -> CostSummary:
    """상업 조건 탭 (FR-16): 비용 조건 요약과 기술 판단에서 생긴 상업 영향. 금액 계산 없음."""
    _summary(run_id)
    with connect() as conn:
        return cost_summary(conn, run_id)


@router.get("/runs/{run_id}/outputs")
def run_outputs(run_id: int, list_kind: str | None = None) -> list[OutputItem]:
    _summary(run_id)
    with connect() as conn:
        return queries.run_outputs(conn, run_id, list_kind)


@router.get("/runs/{run_id}/outputs/export", response_class=Response,
            responses=_file(DOCX_TYPE))
def export_outputs(run_id: int, list_kind: str = Query(pattern="^(DEVIATION|QUERY)$")) -> Response:
    """일탈 목록·질의서 초안 Word 파일 (SCR-08-11). 항목이 없으면 파일을 만들지 않는다."""
    _summary(run_id)
    with connect() as conn:
        items = [i for i in queries.run_outputs(conn, run_id, list_kind)
                 if i["status"] != "REMOVED"]
        if not items:
            label = "일탈" if list_kind == "DEVIATION" else "질의"
            raise HTTPException(409, f"{label} 후보가 없습니다. 목록 초안을 생성할 수 없습니다.")
        name, body = outputs_docx(conn, run_id, list_kind)
    return Response(body, media_type=DOCX_TYPE,
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})


@router.get("/runs/{run_id}/tbe")
def get_tbe(run_id: int, include: str = Query("all", pattern="^(all|confirmed)$"),
            lang: str = Query("en", pattern="^(en|ko|both)$"),
            base: str = Query("now", pattern="^(now|v1)$")) -> Tbe:
    """TBE 준수표 미리보기 (SCR-09). 엑셀과 같은 줄."""
    _summary(run_id)
    with connect() as conn:
        try:
            return tbe.tbe(conn, run_id, include, lang, base)
        except tbe.NotApproved as exc:
            raise HTTPException(409, str(exc)) from exc


@router.get("/runs/{run_id}/tbe/export", response_class=Response,
            responses=_file(XLSX_TYPE))
def export_tbe(run_id: int, include: str = Query("all", pattern="^(all|confirmed)$"),
               lang: str = Query("en", pattern="^(en|ko|both)$"),
               base: str = Query("now", pattern="^(now|v1)$")) -> Response:
    """TBE 준수표 엑셀 파일. X-Row-Count = 줄 수."""
    _summary(run_id)
    with connect() as conn:
        try:
            name, body, n = tbe.tbe_xlsx(conn, run_id, include, lang, base)
        except tbe.NotApproved as exc:
            raise HTTPException(409, str(exc)) from exc
    return Response(body, media_type=XLSX_TYPE, headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}",
        "X-Row-Count": str(n), "Access-Control-Expose-Headers": "X-Row-Count"})


@router.get("/runs/{run_id}/datasheets")
def get_datasheets(run_id: int) -> list[DatasheetInfo]:
    """판정이 있는 고객 표(데이터시트) 목록 (SCR-10)."""
    _summary(run_id)
    with connect() as conn:
        return datasheet.datasheets(conn, run_id)


@router.get("/runs/{run_id}/datasheet")
def get_datasheet(run_id: int, table_id: int) -> Datasheet:
    """데이터시트 한 장 미리보기. 엑셀과 같은 줄."""
    _summary(run_id)
    with connect() as conn:
        try:
            return datasheet.datasheet(conn, run_id, table_id)
        except datasheet.NotFound as exc:
            raise HTTPException(404, str(exc)) from exc


@router.get("/runs/{run_id}/datasheet/export", response_class=Response,
            responses=_file(XLSX_TYPE))
def export_datasheet(run_id: int, table_id: int) -> Response:
    """데이터시트 엑셀 파일. X-Row-Count = 줄 수."""
    _summary(run_id)
    with connect() as conn:
        try:
            name, body, n = datasheet.datasheet_xlsx(conn, run_id, table_id)
        except datasheet.NotFound as exc:
            raise HTTPException(404, str(exc)) from exc
    return Response(body, media_type=XLSX_TYPE, headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}",
        "X-Row-Count": str(n), "Access-Control-Expose-Headers": "X-Row-Count"})


@router.get("/runs/{run_id}/submission-check")
def get_submission_check(run_id: int) -> SubmissionCheck:
    _summary(run_id)
    with connect() as conn:
        result = queries.submission_check(conn, run_id)
    if result is None:
        raise HTTPException(404, "아직 누락 점검 결과가 없습니다.")
    return result


@router.post("/runs/{run_id}/submission-check")
def run_submission_check(run_id: int) -> SubmissionCheck:
    _summary(run_id)
    with connect() as conn:
        return check_submission(conn, run_id)


@router.get("/runs/{run_id}/checks")
def run_checks(run_id: int) -> list[EngineeringCheck]:
    _summary(run_id)
    with connect() as conn:
        return queries.run_checks(conn, run_id)


@router.get("/runs/{run_id}/proposals")
def run_proposals(run_id: int) -> list[Proposal]:
    _summary(run_id)
    with connect() as conn:
        return queries.run_proposals(conn, run_id)


@router.post("/runs/{run_id}/actions")
def act(run_id: int, body: Action) -> ActionResult:
    """후보 하나를 확정·수정·반려(제안 포인트는 채택·버림·수정)하고 이력을 남긴다."""
    with connect() as conn, _ai(conn, "REVIEW_ACTION", run_id) as ctx:
        return _review(lambda: review.act(ctx, run_id, body.target,
                                          body.target_id, body.action, body.value,
                                          body.reason, body.actor_id))


@router.post("/runs/{run_id}/requirements/{requirement_id}/type")
def edit_type(run_id: int, requirement_id: int, body: TypeEdit) -> TypeEditResult:
    """사람이 요구사항의 주 유형을 고친다 (add-type-examples). 엔지니어·승인자만."""
    _summary(run_id)
    with connect() as conn:
        actor_id = body.actor_id or review.default_user(conn, "ENGINEER")
        return _review(lambda: review.set_type(conn, run_id, requirement_id, body.type_code,
                                               body.reason, actor_id))


@router.post("/runs/{run_id}/actions/bulk")
def act_bulk(run_id: int, body: BulkAction) -> BulkResult:
    """여러 판정을 한 번에 제안대로 확정한다 (수정·반려는 한 줄씩)."""
    if body.target != "judgment" or body.action != "CONFIRM":
        raise HTTPException(400, "한꺼번에는 판정 확정만 할 수 있습니다.")
    with connect() as conn, _ai(conn, "BULK_CONFIRM", run_id) as ctx:
        return _review(lambda: review.bulk_confirm(ctx, run_id, body.ids, body.actor_id))


@router.get("/runs/{run_id}/history")
def history(run_id: int, target: str | None = None, target_id: int | None = None) -> list[LogEntry]:
    _summary(run_id)
    with connect() as conn:
        return review.history(conn, run_id, target, target_id)


@router.post("/runs/{run_id}/finish-review")
def finish_review(run_id: int, body: Submit) -> SubmitResult:
    """결재 상신. 결재자와 상신 의견을 받아 승인 대기로 둔다 (걸린 기준이 없어도)."""
    with connect() as conn:
        return _review(lambda: review.finish_review(conn, run_id, body.approver_id,
                                                    body.comment, body.actor_id))


@router.post("/runs/{run_id}/withdraw")
def withdraw(run_id: int, body: Actor) -> StageResult:
    """결정 전인 상신을 취소하고 담당자 확인으로 되돌린다."""
    with connect() as conn:
        return _review(lambda: review.withdraw(conn, run_id, body.actor_id))


@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id: int, body: Actor) -> RunSummary:
    """처리 중인 검토를 취소한다. 처리는 다음 진행 기록 때 멈추고 처리 실패가 된다."""
    with connect() as conn:
        _review(lambda: run_control.request_cancel(conn, run_id, body.actor_id))
    return _summary(run_id)


@router.post("/runs/{run_id}/retry", status_code=202)
def retry_run(run_id: int, body: Actor, background: BackgroundTasks) -> RunSummary:
    """실패·취소한 검토를 같은 파일·분류로 다시 처리한다. 처리한 문서는 다시 쓴다."""
    with connect() as conn:
        paths, choices = _review(lambda: run_control.prepare_retry(conn, run_id, body.actor_id))
    background.add_task(run_to_end, run_id, paths, choices)
    return _summary(run_id)


@router.post("/runs/{run_id}/documents", status_code=202)
async def add_documents(run_id: int, files: list[UploadFile], background: BackgroundTasks,
                        actor_id: int | None = Form(None),
                        choices: str | None = Form(None)) -> RunSummary:
    """분석을 마친 검토(담당자 확인 단계)에 정정본·추가 문서를 더해 같은 검토를 다시 분석한다.

    처리한 문서는 다시 쓰고, 같은 줄의 확정·수정·반려는 이어받는다 (FR-01 ⑤, FR-10 ⑤).
    choices는 더하는 파일의 분류 JSON ({파일 이름: {bundle, doc_kind}}).
    """
    try:
        chosen = TypeAdapter(Choices).validate_json(choices) if choices else {}
    except ValidationError as exc:
        raise HTTPException(400, f"문서 분류 값이 틀렸습니다: {exc.errors()[0]['msg']}") from exc
    new_paths = await _save_uploads(files)
    added = {name: c.model_dump(exclude_none=True) for name, c in chosen.items()}
    with connect() as conn:
        paths, merged = _review(lambda: doc_add.prepare_add(conn, run_id, new_paths, added,
                                                            actor_id))
    background.add_task(run_to_end, run_id, paths, merged)
    return _summary(run_id)


@router.post("/runs/{run_id}/rewind", status_code=202)
def rewind(run_id: int, body: Rewind, background: BackgroundTasks) -> RunSummary:
    """담당자 확인 단계의 검토를 고른 처리 단계부터 다시 처리한다 (add-step-rewind, C2).

    같은 줄의 사람 확정·수정·반려와 위험 조건 확인은 이어받는다 (CR-08, FR-10 ⑤).
    """
    with connect() as conn:
        paths, choices = _review(lambda: doc_add.prepare_rewind(conn, run_id, body.step,
                                                                body.reason, body.actor_id))
    background.add_task(run_to_end, run_id, paths, choices, body.step)
    return _summary(run_id)


@router.get("/runs/{run_id}/compare")
def compare_targets(run_id: int) -> CompareTargets:
    """지난 RFP 비교 대상: 고객사 글자가 같은 처리를 마친 다른 검토 (SCR-08-7)."""
    with connect() as conn:
        try:
            return past_compare.targets(conn, run_id)
        except past_compare.NotFound as exc:
            raise HTTPException(404, str(exc)) from exc


@router.get("/runs/{run_id}/compare/{other_id}")
def compare_runs(run_id: int, other_id: int) -> PastCompare:
    """이번 검토와 지난 검토의 달라진 요구(값 바뀜·새로 생김·사라짐)와 판정 변화."""
    with connect() as conn:
        try:
            return past_compare.compare(conn, run_id, other_id)
        except past_compare.NotFound as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc


@router.get("/runs/{run_id}/approval")
def get_approval(run_id: int) -> ApprovalScreen:
    with connect() as conn:
        screen = _review(lambda: review.approval(conn, run_id))
        screen["read_unchecked"] = read_checks.unchecked(conn, run_id)   # 문서 읽기 점검 미확인
        return screen


@router.get("/runs/{run_id}/read-checks")
def run_read_checks(run_id: int) -> list[ReadCheck]:
    """문서 읽기 점검: 시스템이 제대로 읽지 못한 곳과 사람이 확인한 기록 (SCR-08-2)."""
    with connect() as conn:
        return _review(lambda: read_checks.read_checks(conn, run_id))


@router.post("/runs/{run_id}/read-checks/{key}")
def check_read(run_id: int, key: str, body: Actor) -> ReadCheck:
    with connect() as conn:
        return _review(lambda: read_checks.set_checked(conn, run_id, key, True, body.actor_id))


@router.delete("/runs/{run_id}/read-checks/{key}")
def uncheck_read(run_id: int, key: str, actor_id: int | None = None) -> ReadCheck:
    with connect() as conn:
        return _review(lambda: read_checks.set_checked(conn, run_id, key, False, actor_id))


@router.post("/runs/{run_id}/approval")
def decide(run_id: int, body: Decision) -> DecisionResult:
    with connect() as conn:
        screen = _review(lambda: review.decide(conn, run_id, body.decision, body.comment,
                                               body.actor_id))
        screen["read_unchecked"] = read_checks.unchecked(conn, run_id)
        return screen


@router.post("/runs/{run_id}/reopen")
def reopen(run_id: int, body: Actor) -> StageResult:
    with connect() as conn:
        return _review(lambda: review.reopen(conn, run_id, body.actor_id))


@router.get("/runs/{run_id}/deliverables")
def deliverables(run_id: int) -> Deliverables:
    """전달 대상: 빼지 않은 목록, 확정한 보증값, 채택한 제안 포인트만 (AR-08)."""
    _summary(run_id)
    with connect() as conn:
        return review.deliverables(conn, run_id)


@router.get("/tasks")
def my_tasks(user_id: int) -> MyTasks:
    """고른 사용자의 "내 할 일": 엔지니어·승인자는 멈춘 검토, 담당자는 받은 할 일 (FR-11)."""
    with connect() as conn:
        return _review(lambda: review.my_tasks(conn, user_id))


@router.get("/runs/{run_id}/assignments")
def run_assignments(run_id: int, role: str) -> list[Assignment]:
    _summary(run_id)
    with connect() as conn:
        return review.assignments_for(conn, role, run_id)


@router.get("/assignments")
def role_assignments(role: str | None = Query(None, pattern="^(COST|QUALITY|SALES)$")
                     ) -> list[Assignment]:
    """협조 요청 현황 (SCR-13): 한 수신 부서(없으면 세 부서)에 보낸 요청을 모든 검토에서 모은다."""
    with connect() as conn:
        return review.assignments_for(conn, role)


@router.post("/assignments/export", response_class=Response, responses=_file(XLSX_TYPE))
def export_assignments(body: ExportAssignments) -> Response:
    """화면이 거른 협조 요청을 엑셀로 (SCR-13 내보내기). X-Row-Count = 줄 수."""
    with connect() as conn:
        try:
            name, data, n = assignment_export.assignments_xlsx(conn, body.role,
                                                               body.assignment_ids)
        except assignment_export.NothingToExport as e:
            raise HTTPException(400, str(e)) from e
    return Response(data, media_type=XLSX_TYPE, headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}",
        "X-Row-Count": str(n), "Access-Control-Expose-Headers": "X-Row-Count"})


@router.put("/assignments/{assignment_id}")
def update_assignment(assignment_id: int, body: TaskStatus) -> AssignmentStatus:
    """엔지니어가 회신 받음을 기록하거나 되돌린다 (메일 보냄 ↔ 회신 받음)."""
    with connect() as conn:
        return _review(lambda: review.set_assignment_status(conn, assignment_id, body.status,
                                                            body.actor_id, body.reply_note))


@router.post("/runs/{run_id}/assignments/send")
def send_assignments(run_id: int, body: SendRequests) -> SendResult:
    """엔지니어가 고른 요청을 부서 주소로 보낸다 (판정 없는 요청, 실패·주소 없음 다시 보내기)."""
    _summary(run_id)
    with connect() as conn:
        actor_id = body.actor_id or review.default_user(conn, "ENGINEER")
        if _review(lambda: review._user_role(conn, actor_id)) != "ENGINEER":
            raise HTTPException(403, "협조 요청은 기술 검토 엔지니어만 보낼 수 있습니다.")
        conn.execute("UPDATE assignment SET mail_error = NULL WHERE run_id = %s "
                     "AND assignment_id = ANY(%s) AND mail_sent_at IS NULL",
                     (run_id, body.assignment_ids))
        llm = make_llm(get_settings())
        with ai_usage.tracked(conn, "HANDOFF_ASK", run_id, llm):
            return send_requests(conn, run_id, body.assignment_ids, actor_id, llm,
                                 resend=body.resend)


# ── 영업 인계 (add-submission-package, FR-11 확장) ──────────────

def _engineer(conn, actor_id: int | None) -> int:
    actor = actor_id or review.default_user(conn, "ENGINEER")
    if _review(lambda: review._user_role(conn, actor)) != "ENGINEER":
        raise HTTPException(403, "영업에 넘기기는 기술 검토 엔지니어만 할 수 있습니다.")
    return actor


@router.post("/runs/{run_id}/datasheet/handoff")
def handoff_datasheet(run_id: int, body: HandoffRequest) -> HandoffResult:
    """데이터시트 한 장을 영업 주소로 보낸다. 후보 칸이 남으면 409."""
    _summary(run_id)
    if body.table_id is None:
        raise HTTPException(422, "넘길 데이터시트(table_id)를 정해 주세요.")
    with connect() as conn:
        actor = _engineer(conn, body.actor_id)
        try:
            return sales_handoff.send_datasheet(conn, run_id, body.table_id, actor)
        except datasheet.NotFound as exc:
            raise HTTPException(404, str(exc)) from exc
        except sales_handoff.HandoffRefused as exc:
            raise HTTPException(409, str(exc)) from exc


@router.get("/runs/{run_id}/package", response_class=Response, responses=_file(ZIP_TYPE))
def download_package(run_id: int) -> Response:
    """인계 패키지 zip (결재 승인 뒤). 승인 전이면 409."""
    _summary(run_id)
    with connect() as conn:
        try:
            name, body, _ = sales_handoff.build_package(conn, run_id)
        except sales_handoff.HandoffRefused as exc:
            raise HTTPException(409, str(exc)) from exc
    return Response(body, media_type=ZIP_TYPE,
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})


@router.post("/runs/{run_id}/package/handoff")
def handoff_package(run_id: int, body: HandoffRequest) -> HandoffResult:
    """인계 패키지를 영업 주소로 보낸다."""
    _summary(run_id)
    with connect() as conn:
        actor = _engineer(conn, body.actor_id)
        try:
            return sales_handoff.send_package(conn, run_id, actor)
        except sales_handoff.HandoffRefused as exc:
            raise HTTPException(409, str(exc)) from exc


@router.get("/runs/{run_id}/handoffs")
def list_handoffs(run_id: int) -> list[SalesHandoff]:
    """영업에 넘긴 기록, 최근 것부터."""
    _summary(run_id)
    with connect() as conn:
        return sales_handoff.handoffs(conn, run_id)
