"""API 응답 모델 (change update-api-contract, 명세 api-contract).

조회 함수(`pipeline/queries.py` 등)는 dict를 돌려주고, FastAPI가 이 모델로 검사해 내보낸다.
- 모르는 칸은 받지 않는다(extra="forbid"). 조회가 칸을 더하면 여기에도 더해야 테스트가 통과한다.
- 빈 값은 None 그대로 보낸다. 기본값으로 채우지 않는다 (CR-04).
- DB에서 NULL이 될 수 있는 칸은 `| None`. DB CHECK로 정해진 값은 Literal.
- 근거 응답(판정·보증값·손실·검산·일탈·질의·제안 포인트)의 원문 위치는 하나 이상 (CR-02·03).
- NUMERIC 칸은 JSON 숫자(float)로 보낸다.
모델 이름은 화면 타입 이름과 같다 (frontend/src/api.gen.ts로 만들어짐).
"""

from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Out(BaseModel):
    model_config = ConfigDict(extra="forbid")


Stage = Literal["PROCESSING", "ENGINEER_REVIEW", "APPROVAL", "APPROVED", "REJECTED", "FAILED"]
Role = Literal["ENGINEER", "COST", "QUALITY", "SALES", "APPROVER"]
JudgmentResult = Literal["COMPLY", "DEVIATION_CANDIDATE", "QUERY_CANDIDATE", "NEEDS_REVIEW",
                         "WARRANTY_TO_FILL"]
NumberCheck = Literal["OK", "MISMATCH"]
DraftedBy = Literal["CODE", "AI", "ENGINEER"]
TaskState = Literal["TODO", "DOING", "DONE"]


class Location(Out):
    """원문 위치: 파일 번호 + 절 또는 표 + 행 (CR-02). 절·표·항목·행은 있는 것만 있다."""
    file_no: int
    section_no: str | None
    section_title: str | None
    table_name: str | None
    item_no: str | None
    line_start: int | None
    line_end: int | None
    page: int | None = None         # PDF 쪽 번호 (add-pdf-page-location). docx는 없음


# 근거 응답의 원문 위치: 하나 이상
Locations = Annotated[list[Location], Field(min_length=1)]


# ── 사용자·검토 실행 ─────────────────────────────────────────

class User(Out):
    user_id: int
    user_name: str
    role: Role


class ReviewFields(Out):
    """사람이 넣는 검토 정보 (add-review-info)와 연결된 사업 (add-project-status). 빈 값은 null."""
    project_name: str | None
    review_name: str | None
    customer_name: str | None
    country: str | None
    due_date: date | None
    engineer_id: int | None
    business_id: int | None
    business_no: str | None


class StepDetail(Out):
    """문서 읽기 단계 안의 세부 진행 (처리 상태 화면). AI 일만 줄 수가 있다."""
    part: Literal["classify", "structure", "extract", "label", "save", "type"]
    done: int | None
    total: int | None
    file_index: int
    file_count: int


class Revision(Out):
    """문서 추가로 다시 분석한 결과 (add-revision-notice).

    줄 수는 같은 줄(요구값·비교 제품·비교 규칙) 기준."""
    no: int                             # 개정 번호 (문서를 더한 횟수)
    at: datetime                        # 다시 판정한 시각
    files: list[str]                    # 이번에 더한 파일 이름
    changed: int                        # 판정 값이 바뀐 줄
    added: int                          # 새로 생긴 줄
    removed: int                        # 사라진 줄


class RunSummary(ReviewFields):
    run_id: int
    review_no: str
    engineer_name: str | None
    stage: Stage
    dict_version: str
    llm_model: str | None
    step: str | None
    step_detail: StepDetail | None
    step_updated_at: datetime
    failed_step: str | None
    error_message: str | None
    cancel_requested_at: datetime | None    # 취소를 요청했으면 그 시각 (멈춘 뒤에도 남음)
    retries: int                            # 다시 시도한 횟수
    retryable: bool                         # 처리 실패이고 다시 돌릴 파일 정보가 있음
    started_at: datetime
    finished_at: datetime | None
    documents: int
    requirements: int
    risks: int
    judgments: int
    deviation_candidates: int
    output_items: int
    check_violations: int
    proposals: int
    revision: Revision | None = None    # 문서 추가로 다시 분석했으면 마지막 개정


class SummaryPart(Out):
    """요약 문장 조각 (add-screen-summary).

    link면 href는 화면 주소(#는 화면이 붙임), strong은 강조."""
    t: str
    kind: Literal["text", "link", "strong"]
    href: str | None


class ScreenSummary(Out):
    """요약 상자 문장 (add-screen-summary, 결정 Q1).

    코드가 틀에 채운 문장, 같은 데이터면 같은 문장."""
    sentences: list[list[SummaryPart]]
    meta: str | None                    # 머리 한 줄 (검토 요약만: 문서·요구사항·판정 수, 분석 시간)
    written_by: Literal["CODE"]
    made_at: datetime


class RunListItem(ReviewFields):
    run_id: int
    review_no: str
    engineer_name: str | None
    stage: Stage
    step: str | None
    step_detail: StepDetail | None
    step_updated_at: datetime
    failed_step: str | None
    error_message: str | None
    started_at: datetime
    finished_at: datetime | None
    files: str | None
    requirements: int
    risks: int
    deviation_candidates: int
    proposals: int
    # 가장 최근 상신의 결재 정보 (취소했거나 상신 전이면 비어 있음, update-review-list-approval)
    approver_id: int | None
    approver: str | None
    requested_by_id: int | None
    requested_by: str | None
    requested_at: datetime | None
    decision: Literal["APPROVED", "REJECTED"] | None
    decided_at: datetime | None
    # 문서 추가로 다시 분석했으면 마지막 개정 (add-revision-notice)
    revision: Revision | None = None


class RunDocument(Out):
    document_id: int
    file_no: int
    file_name: str
    bundle: Literal["A", "B", "C", "D"]
    doc_kind: str
    language: str
    standard_system: str | None
    judge_target: bool
    readable: bool
    classify_by: str | None
    needs_review: bool
    line_basis: str | None
    requirements: int
    processor: str | None = None            # 처음 고른 처리기 (C1). GENERAL = 일반, 예전 문서 비움
    process_check: str | None = None        # 처리 뒤 점검에 걸린 이유 (통과면 비움)
    reprocessed: bool = False               # 점검 뒤 떨어진 부분을 일반 처리기로 다시 물음
    reprocessed_lines: int = 0              # 다시 물은 줄 수 (update-partial-reprocess)
    ocr_lines: int = 0                      # OCR로 읽은 줄 수 (add-ocr). 있으면 글자 확인 필요


class SourceLine(Out):
    line_no: int
    text: str


class DocumentLines(Out):
    """원문 줄 범위 (add-judgment-view). partial이면 파일이 없어 DB에 남은 줄만 왔다."""
    file_no: int
    file_name: str
    line_from: int
    line_to: int
    partial: bool
    lines: list[SourceLine]


DocKind = Literal["BID_FORM", "REQUIREMENT_SPEC", "PURCHASE_SPEC", "TEST_SPEC", "SUPPLIER_SPEC",
                  "BOQ", "UNKNOWN"]


class DocumentPreview(Out):
    """분석 전 분류 추천 (저장하지 않음). 묶음·판정 대상은 코드 규칙의 추천이다."""
    file_name: str
    in_catalog: bool
    file_no: int | None
    doc_kind: DocKind
    bundle: Literal["A", "B", "C", "D"]
    language: str
    standard_system: str | None
    readable: bool
    judge_target: bool
    needs_review: bool
    reason: str


class DocumentPair(Out):
    pair_id: int
    file_no_a: int
    file_no_b: int
    relation: str
    status: str
    evidence: str | None


# ── 요구사항·위험 조건 ──────────────────────────────────────

class TypeTag(Out):
    type_code: str
    is_primary: bool
    decided_by: Literal["RULE", "AI", "HUMAN"]
    rule_code: str | None


class ReqValue(Out):
    value_seq: int
    raw_text: str | None
    cell_form: str
    num_value: float | None
    operator: str | None
    unit_raw: str | None
    cond_time_s: float | None
    cond_raw: str | None
    item_key: str | None
    target_object: str | None
    basis_standard: str | None
    delegated_std: str | None
    equipment_key: str | None
    flag: str | None


class Requirement(Out):
    """요구사항. 목록(문서 읽기 점검)은 원문 위치가 없는 줄도 보여 준다."""
    requirement_id: int
    file_no: int
    file_name: str
    source_kind: str
    req_kind: str
    text_raw: str
    extracted_by: Literal["RULE", "AI", "OCR"]      # OCR: 그림 속 글자에서 뽑은 줄 (add-ocr)
    confidence: float | None
    is_assumed: bool
    rule_id: str | None
    supplier_mark: str | None
    dedup_of: int | None
    locations: list[Location]
    types: list[TypeTag]
    values: list[ReqValue]


class RiskMember(Out):
    requirement_id: int
    text_raw: str
    value_raw: str | None
    locations: list[Location]


class Risk(Out):
    risk_id: int
    risk_kind: str
    status: str
    item_key: str | None
    item_name: str | None
    facts: str | None
    explanation_ai: str | None
    # 근거 대조에서 AI 설명을 버린 이유 (update-ai-answer-checks). 저장했거나 AI 없이 돌면 null
    explanation_drop_reason: Literal["UNKNOWN_EVIDENCE", "QUOTE_NOT_FOUND",
                                     "NUMBER_NOT_ALLOWED", "FORMAT_ERROR"] | None
    # 검증 에이전트 결과 (add-claim-verifier). 설명이 없거나 검증 전이면 null
    explanation_check: Literal["VERIFIED", "NEEDS_REVIEW"] | None
    expression: str | None
    members: list[RiskMember]


# ── 판정 ────────────────────────────────────────────────────

class PastDecision(Out):
    """다른 검토에서 사람이 확정·수정한 같은 요구·같은 제품 판정 (add-review-memory). 힌트일 뿐."""
    run_id: int
    review_no: str
    result: JudgmentResult
    review_status: Literal["CONFIRMED", "EDITED"]
    decided_by: str | None
    decided_at: datetime | None
    reason: str | None
    same: bool                          # 지금 판정 값과 같은지
    # MEANING: 뜻이 비슷한 지난 확정 (add-meaning-search)
    match: Literal["TEXT", "MEANING"] = "TEXT"
    score: float | None = None          # 뜻으로 찾았으면 벡터 코사인


class Judgment(Out):
    judgment_id: int
    requirement_id: int
    equipment_group: str
    result: JudgmentResult
    reason_code: str | None
    reason_text: str | None
    product_code: str | None
    product_selected_by: Literal["AUTO", "ENGINEER"] | None
    product_value_raw: str | None
    product_value_unit: str | None
    margin_value: float | None
    margin_kind: Literal["DIFF", "RATIO", "TIME_RATIO"] | None
    margin_direction: Literal["STRENGTH", "NOT_STRENGTH", "NOT_CALC"]
    is_assumed: bool
    review_status: Literal["CANDIDATE", "CONFIRMED", "EDITED", "REJECTED"]
    req_value_raw: str | None
    req_num: float | None
    unit_raw: str | None
    cond_time_s: float | None
    item_key: str | None
    item_name: str | None
    item_name_raw: str | None
    type_code: str | None
    type_name: str | None
    past_decision: PastDecision | None
    query_sent_at: datetime | None = None       # 질의 보냄 표시 시각 (add-query-sent)
    query_sent_by_name: str | None = None
    # 마지막 개정에서 바뀜·추가 (add-revision-notice)
    revised: Literal["CHANGED", "ADDED"] | None = None
    locations: Locations


class JudgmentCounts(Out):
    by_result: dict[JudgmentResult, int]
    total: int
    unconfirmed: int
    unconfirmed_comply: int
    past_seen: int                      # 지난 사람 판정이 있는 줄
    past_differs: int                   # 그중 지금 판정과 다른 줄


class Equipment(Out):
    equipment_group: str
    label: str | None
    family: str | None
    products: list[str] | None
    selected_by: str | None
    chosen_product: str | None
    candidates: list[str]
    judgments: int
    deviations: int
    ambiguous: int


class ProductSwitch(Out):
    """비교 제품 바꾸기 뒤 다시 만든 줄 수."""
    judgment_count: int
    check_count: int
    warranty_count: int
    loss_count: int
    output_count: int
    proposal_count: int
    assignment_count: int


# ── 보증값·손실·검산·산출물·제안 포인트 ──────────────────────

class CompareTarget(Out):
    """지난 RFP 비교 대상: 같은 고객사의 처리를 마친 다른 검토 (add-past-compare)."""
    run_id: int
    review_no: str
    stage: Stage
    started_at: datetime
    project_name: str | None
    review_name: str | None
    customer_name: str | None
    files: str | None
    judgments: int
    products: list[str]


class CompareTargets(Out):
    customer_name: str | None          # 이번 검토의 고객사 (비면 대상 없음)
    targets: list[CompareTarget]


class CompareRow(Out):
    kind: Literal["chg", "new", "del"]
    equipment: str
    item_name: str
    item_raw: str | None               # 표의 항목 이름 (영문 원문, 표준 항목 이름과 다를 때)
    before: str
    after: str
    before_result: JudgmentResult | None
    after_result: JudgmentResult | None
    note: str
    requirement_id: int | None         # 이번 검토의 요구사항 (사라진 줄은 없음)


class PastCompare(Out):
    target: CompareTarget
    rows: list[CompareRow]
    same: int                          # 값과 판정이 같아 숨긴 줄 수


class Warranty(Out):
    candidate_id: int
    judgment_id: int
    requirement_id: int
    equipment_group: str
    item_key: str | None
    item_name: str | None
    item_name_raw: str | None
    candidate_value: str | None
    candidate_unit: str | None
    source_kind: Literal["PM", "FIXED", "ENGINEER"] | None
    product_code: str | None
    pm_column: str | None
    fixed_key: str | None
    status: Literal["CANDIDATE", "EMPTY_REVIEW", "CONFIRMED", "REJECTED"]
    reason_code: str | None
    is_assumed: bool
    locations: Locations


class LossAmounts(Out):
    """종류별 가산액 (단가 × 손실값). 손실값이 없으면 null."""
    noload: float | None
    load: float | None
    aux: float | None


class Loss(Out):
    loss_calc_id: int
    requirement_id: int
    product_code: str | None
    price_noload: float
    price_load: float
    price_aux: float
    price_unit: str | None
    loss_noload_kw: float | None
    loss_load_kw: float | None
    loss_aux_kw: float | None
    total_usd: float | None
    formula: str | None
    status: Literal["CALCULATED", "NEEDS_REVIEW"]
    reason_code: str | None
    is_assumed: bool
    price_requirement_ids: list[int] | None
    amounts: LossAmounts
    locations: Locations
    price_locations: list[Location]


class LossResult(Out):
    """손실값을 넣고 다시 계산한 결과. 사람이 넣은 값이라 항상 팀 가정 (CR-06)."""
    total_usd: float | None
    formula: str | None
    status: Literal["CALCULATED", "NEEDS_REVIEW"]
    is_assumed: Literal[True]


class EngineeringCheck(Out):
    check_id: int
    rule_code: str
    result: Literal["PASS", "VIOLATION", "NEEDS_REVIEW"]
    reason_code: str | None
    expected_ka: float | None
    factor: float | None
    requirement_id: int
    ik_requirement_id: int
    peak_item_key: str
    peak_ka: float
    peak_raw: str | None
    ik_item_key: str
    ik_ka: float
    ik_raw: str | None
    frequency_hz: float | None
    locations: Locations
    ik_locations: list[Location]


class OutputSource(Out):
    source_seq: int
    judgment_id: int | None
    risk_id: int | None
    check_id: int | None
    requirement_id: int | None


class OutputItem(Out):
    item_id: int
    list_kind: Literal["DEVIATION", "QUERY"]
    list_name: str | None
    text_draft: str
    number_check: NumberCheck
    number_detail: str | None
    drafted_by: DraftedBy
    status: Literal["DRAFT", "CONFIRMED", "REMOVED"]
    is_assumed: bool
    basis_requirement_id: int | None
    sources: list[OutputSource]
    locations: Locations
    linked_items: list[int]


class Proposal(Out):
    point_id: int
    point_kind: Literal["MARGIN", "LOSS", "FIELD"]
    requirement_id: int
    product_code: str | None        # 현장 이력(FIELD)은 제품 행 대신 연결표 줄이 근거
    judgment_id: int | None
    loss_calc_id: int | None
    fault_link_id: int | None
    text_draft: str
    basis: str | None
    number_check: NumberCheck
    number_detail: str | None
    drafted_by: DraftedBy
    is_assumed: bool
    status: Literal["CANDIDATE", "ADOPTED", "DISCARDED", "EDITED"]
    locations: Locations


class SubmissionCheck(Out):
    deviation_candidates: int
    deviation_listed: int
    missing_judgment_ids: list[int]
    open_queries: int
    ar_codes: list[str]
    checked_at: datetime | None = None      # 저장된 확인 결과에만 있음


# ── TBE·데이터시트 ──────────────────────────────────────────

class TbeRow(Out):
    no: int
    judgment_id: int
    result: JudgmentResult
    item: str
    item_ko: str | None
    requirement: str
    verdict: str
    offered: str
    confirmed: bool
    assumed: bool
    status: str
    file_name: str
    where: str
    source: str


class TbeCounts(Out):
    rows: int
    comply: int
    deviation: int
    query: int
    review: int
    candidates: int
    no_location: int


class Tbe(Out):
    file_name: str
    review_no: str
    project_name: str | None
    review_name: str | None
    rows: list[TbeRow]
    counts: TbeCounts


class DatasheetInfo(Out):
    table_id: int
    table_name: str
    file_name: str
    rows: int
    empty: int


class DatasheetRow(Out):
    judgment_id: int
    candidate_id: int | None
    target: Literal["judgment", "warranty"]
    no: str
    item: str
    item_en: str
    unit: str
    requirement: str
    value: str | None
    basis: str
    why: str
    state: Literal["ok", "cand", "empty"]
    status: str
    assumed: bool


class DatasheetCounts(Out):
    rows: int
    ok: int
    cand: int
    empty: int


class Datasheet(Out):
    file_name: str
    review_no: str
    table_id: int
    table_name: str
    source_file: str
    rows: list[DatasheetRow]
    counts: DatasheetCounts


# ── 확인·결재 ───────────────────────────────────────────────

class ActionResult(Out):
    """확정·수정·반려 하나. 바뀌기 전·후 줄은 대상 표마다 칸이 달라 자유 형식이다."""
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    submission_check: SubmissionCheck | None


class BulkSkipped(Out):
    """한꺼번에 확정에서 뺀 줄 (update-bulk-confirm-guard). 한 줄씩 확인해 확정한다."""
    judgment_id: int
    reason: Literal["CHECK", "MISMATCH", "NO_VALUE"]   # 검산 위반·확인 필요 / 숫자 불일치 / 값 없음


class BulkResult(Out):
    confirmed: int
    skipped: list[BulkSkipped]
    submission_check: SubmissionCheck | None


class TypeEditResult(Out):
    """사람 유형 고치기 결과 (add-type-examples). NONE은 미분류."""
    requirement_id: int
    before: str
    after: str


class LogEntry(Out):
    log_id: int
    target_table: str
    target_id: int
    action: str
    before_value: dict[str, Any] | None
    after_value: dict[str, Any] | None
    reason: str | None
    actor: str | None
    acted_at: datetime
    target_label: str | None   # 바뀐 대상의 이름. 검토 실행·비교 제품은 null


class Criterion(Out):
    ar_code: str
    detail: str
    description: str | None = None      # 결재 화면의 사유에만 있음


class Approval(Out):
    approval_id: int
    decision: Literal["APPROVED", "REJECTED", "WITHDRAWN"] | None
    comment: str | None
    requested_at: datetime
    decided_at: datetime | None
    approver_id: int | None
    approver: str | None
    requested_by_id: int | None
    requested_by: str | None
    request_comment: str | None


class ReviewRatio(Out):
    review: int
    total: int
    threshold: float
    hand_fill: int          # 직접 작성할 칸: 제품표에 연결되지 않은 보증값 빈칸 (비율에서 뺌)


class ApprovalScreen(Out):
    stage: Stage
    approval: Approval | None
    reasons: list[Criterion]
    preview: list[Criterion] | None
    review_ratio: ReviewRatio
    submission_check: SubmissionCheck | None
    read_unchecked: int     # 문서 읽기 점검 미확인 수


class DecisionResult(ApprovalScreen):
    approval_id: int


class SubmitResult(Out):
    stage: Stage
    approval_id: int
    criteria: list[Criterion]


class StageResult(Out):
    stage: Stage
    approval_id: int | None = None


class ReadCheck(Out):
    """문서 읽기 점검 줄 (SCR-08-2). kind: 표·그림·단위·위치."""
    key: str
    kind: str
    what: str
    document_id: int
    file_name: str
    loc: str
    line: int | None
    problem: str
    todo: str
    checked_by: str | None
    checked_at: datetime | None


class DeliverableProposal(Out):
    point_id: int
    point_kind: str
    text_draft: str
    basis: str | None
    is_assumed: bool
    status: str


class DeliverableOutput(Out):
    item_id: int
    list_kind: Literal["DEVIATION", "QUERY"]
    list_name: str | None
    text_draft: str
    status: str
    is_assumed: bool


class DeliverableWarranty(Out):
    candidate_id: int
    judgment_id: int
    candidate_value: str | None
    candidate_unit: str | None
    source_kind: str | None


class Deliverables(Out):
    proposals: list[DeliverableProposal]
    outputs: list[DeliverableOutput]
    warranty: list[DeliverableWarranty]


# ── 할 일 ───────────────────────────────────────────────────

class Assignment(Out):
    assignment_id: int
    run_id: int
    assignee_role: Literal["ENGINEER", "COST", "QUALITY", "SALES"]
    status: TaskState
    repeat_count: int
    sent_at: datetime
    updated_at: datetime | None
    requirement_id: int | None
    requirement_ids: list[int]
    point_id: int | None
    point_kind: str | None
    point_requirement_id: int | None
    type_code: str | None
    type_name: str | None
    assignee: str | None
    text: str
    is_assumed: bool | None
    stage: Stage
    review_no: str
    project_name: str | None
    review_name: str | None
    customer_name: str | None
    country: str | None
    due_date: date | None
    engineer_id: int | None
    engineer_name: str | None
    business_id: int | None
    business_no: str | None
    locations: list[Location]
    file_name: str | None
    mail_sent_at: datetime | None     # 메일 보낸 시각 (sent_at은 할 일을 만든 시각)
    mail_to: str | None
    mail_error: str | None            # "주소 없음" 또는 발송 실패 오류
    sent_by_name: str | None
    dept_address: str | None          # 지금 설정된 부서 주소
    replied_at: datetime | None
    replied_by_name: str | None
    reply_note: str | None
    # 메일에 넣은 부서 관점 확인할 점과 쓴 이 (add-handoff-questions, C4)
    ask_text: str | None = None
    ask_by: Literal["AI", "CODE"] | None = None


class ReviewCard(RunListItem):
    summary: RunSummary
    criteria: list[Criterion]
    approval: Approval | None = None


class MyTasks(Out):
    role: Role
    reviews: list[ReviewCard]
    assignments: list[Assignment]


class AssignmentStatus(Out):
    assignment_id: int
    status: TaskState


class CostCondition(Out):
    """비용 조건 한 줄 (FR-16). 같은 조건이 반복되면 한 줄로 묶는다. 모든 줄은 후보다 (CR-08)."""
    requirement_id: int
    requirement_ids: list[int]
    kind: str                       # 조항 종류 (지체상금, 하자 보증, …, 기타 비용)
    text: str
    values: list[str]               # 값 원문 그대로 (CR-10)
    burden: str | None              # "계약상대자 부담"
    risk: str | None                # "책임 한도 없음", "가격 조정 없음"
    primary_type: str | None
    primary_type_name: str | None
    repeat_count: int
    role: Literal["COST"]
    assignment_id: int | None       # 견적 담당 협조 요청 (없으면 협조 요청 없음)
    request_status: TaskState | None
    mail_error: str | None
    file_name: str | None
    locations: Locations


class CommercialImpact(Out):
    """기술 판단에서 생긴 상업 영향: 손실 환산 가산액(LOSS), 일탈 후보 가격 영향 확인(DEVIATION)."""
    kind: Literal["LOSS", "DEVIATION"]
    loss_calc_id: int | None
    item_id: int | None
    judgment_id: int | None
    product_code: str | None
    total_usd: float | None         # 이미 계산된 가산액. 없으면 확인 필요
    is_assumed: bool
    text: str | None
    locations: Locations


class CostSummary(Out):
    conditions: list[CostCondition]
    impacts: list[CommercialImpact]


class HandoffResult(Out):
    """영업 인계 결과 (add-submission-package). 주소 없음·발송 실패도 200, error를 채운다."""
    handoff_id: int
    sent: bool
    mail_to: str | None
    error: str | None
    empty: int | None        # 데이터시트: 비운 채 넘긴 확인 필요 칸 수
    files: list[str]


class SalesHandoff(Out):
    handoff_id: int
    kind: Literal["DATASHEET", "PACKAGE"]
    table_id: int | None
    file_names: list[str]
    mail_to: str | None
    mail_error: str | None
    sent_at: datetime
    sent_by: int
    sent_by_name: str


class SendResult(Out):
    sent: int           # 메일 보냄이 된 요청 수
    failed: int         # 발송 실패
    no_address: int     # 부서 주소가 설정되지 않음
    mails: int          # 보낸 메일 수 (부서마다 한 통)


# ── 기준 데이터 (제품표·규칙 사전) ──────────────────────────

class Product(Out):
    """제품표 한 줄 (add-reference-views). 빈 칸은 null 그대로 (CR-04)."""
    product_code: str
    product_name: str
    family: str
    rated_voltage_kv: float | None
    rated_current_a: float | None
    short_circuit_ka: float | None
    rated_frequency: str | None
    rated_capacity: float | None
    rated_capacity_unit: str | None
    weight_kg: float | None
    noload_loss_kw: float | None
    load_loss_kw: float | None
    aux_loss_kw: float | None
    loss_is_assumed: bool | None
    lightning_impulse_kv: float | None
    power_freq_withstand_kv: float | None
    switching_impulse_kv: float | None
    peak_current_ka: float | None
    making_current_ka: float | None
    breaking_time_ms: float | None
    closing_time_ms: float | None
    gas_leakage_percent: float | None
    partial_discharge_pc: float | None
    cooling_type: str | None
    insulation_medium: str | None
    maintenance_months: int | None
    service_life_years: int | None
    warranty_months: int | None
    comparison_values_assumed: bool
    comparison_values_source: str | None
    is_assumed: bool
    is_design_card: bool
    source_doc: str | None
    lifecycle_status: str | None
    used: int
    value_columns: list[str]        # 이 제품군에서 판정에 쓰는 칸
    empty_columns: list[str]
    empty_count: int


class ProductUse(Out):
    run_id: int
    review_no: str
    project_name: str | None
    review_name: str | None
    judgment_id: int
    equipment_group: str
    item_name: str | None
    result: JudgmentResult
    product_selected_by: str | None
    item_key: str | None = None        # 표준 항목 (막힌 판정 계산, add-product-view)
    due_date: date | None = None       # 그 검토의 마감 (D-day)


class ProductProposal(Out):
    point_id: int
    run_id: int
    point_kind: str
    status: str
    text_draft: str | None
    is_assumed: bool


class FieldHistory(Out):
    fault_link_id: int
    item_key: str
    item_name: str
    fault_id: str
    symptom: str | None
    root_cause: str | None
    action: str | None
    confirmed_by: str | None
    cases: int


class ProductDetail(Product):
    """제품 하나. 제품표의 모든 칸이 함께 오고, 칸 이름은 제품표 CSV를 따른다."""
    model_config = ConfigDict(extra="allow")
    used_runs: int
    used_in: list[ProductUse]
    proposals: list[ProductProposal]
    field_history: list[FieldHistory]


class ProductFamily(Out):
    family: str
    products: int
    with_empty: int
    empty_cells: int
    assumed: int
    design_cards: int


class CompareRule(Out):
    compare_rule_id: int
    table_name: str | None
    item_no: str | None
    item_key: str | None
    name_ko: str | None
    direction: str
    time_condition: bool
    strength_direction: str | None
    own_strength_direction: str | None     # 이 줄에 적은 강점 방향 (비면 항목 기본값을 씀)
    process_note: str | None
    used: int


class ItemKey(Out):
    item_key: str
    name_ko: str
    default_direction: str
    strength_direction: str
    note: str | None
    pm_column: str | None
    fixed_key: str | None
    aliases: list[str]
    used: int


class DocKindRule(Out):
    """문서 종류 규칙 한 줄. used는 그 종류로 규칙이 분류한 문서 수."""
    doc_kind_rule_id: int
    priority: int
    doc_kind: DocKind
    name_pattern: str
    page_pattern: str | None
    note: str | None
    used: int


class RiskExpression(Out):
    expr_id: int
    expression: str
    language: str
    risk_kind: str
    context_rule: str
    used: int


RuleDictionary = Literal["compare", "risk-expressions", "items", "doc-kinds"]


class RuleEdit(Out):
    """규칙 고침 이력 한 줄 (add-rule-editing).

    row_key는 고치기 전(추가는 추가한) 줄 키, after_key는 고친 뒤 키.
    """
    edit_id: int
    dictionary: RuleDictionary
    row_key: dict[str, Any]
    after_key: dict[str, Any] | None
    action: Literal["ADD", "EDIT", "DELETE"]
    before_value: dict[str, Any] | None
    after_value: dict[str, Any] | None
    reason: str
    actor_id: int
    actor_name: str
    edited_at: datetime
    discarded_at: datetime | None


# ── 사업 현황 (add-project-status) ───────────────────────────
# 범위 상태: 분석 중·분석 실패·판정 확인·협조 대기·결재 대기·반려·제출 준비·제출 완료
RangeState = Literal["an", "fail", "chk", "co", "ap", "rej", "sub", "done"]
BusinessRole = Literal["ENGINEER", "APPROVER", "HELPER", "SALES", "CREATOR"]


class BusinessRange(Out):
    """사업에 연결된 검토 하나 (설비 범위). 상태는 저장하지 않고 계산한다."""
    run_id: int
    review_no: str
    review_name: str | None
    stage: Stage
    due_date: date | None
    started_at: datetime
    engineer_id: int | None
    engineer_name: str | None
    open_requests: int
    state: RangeState


class BusinessListItem(Out):
    business_id: int
    business_no: str
    business_name: str
    customer_name: str | None
    country: str | None
    tender_no: str | None
    order_mode: str | None
    business_due_date: date | None
    due_date: date | None             # 사업 마감, 비면 연결 검토 중 가장 이른 마감
    days_left: int | None
    sales_id: int | None
    sales_name: str | None
    created_by: int
    created_by_name: str
    created_at: datetime
    submitted_at: datetime | None
    my_role: BusinessRole | None
    ranges: list[BusinessRange]


class BusinessSummary(Out):
    open: int
    due3: int
    overdue: int


class BusinessList(Out):
    summary: BusinessSummary
    items: list[BusinessListItem]


class BusinessPerson(Out):
    user_id: int
    user_name: str
    role: Role
    part: Literal["ENGINEER", "APPROVER", "HELPER", "SALES"]
    run_ids: list[int]
    scope: str | None


class BusinessEvent(Out):
    day: date
    kind: Literal["START", "REQUEST", "APPROVED", "REJECTED", "RUN_DUE", "DUE", "SUBMITTED"]
    run_id: int | None
    review_no: str | None


class BusinessDocument(Out):
    run_id: int
    review_no: str
    review_name: str | None
    file_name: str
    doc_kind: str
    bundle: Literal["A", "B", "C", "D"]


class BusinessDetail(BusinessListItem):
    people: list[BusinessPerson]
    schedule: list[BusinessEvent]
    documents: list[BusinessDocument]


class BusinessLog(Out):
    log_id: int
    field: str
    before_value: Any
    after_value: Any
    actor_id: int
    actor_name: str
    acted_at: datetime


class FlowChange(Out):
    """흐름 기록 한 단계에서 바뀐 건수 (add-flow-history). before가 없으면 그 단계에서 처음 생김."""
    key: str                                # documents, judgment_count 등
    before: int | None
    after: int


class FlowStep(Out):
    """흐름 기록의 단계 하나 (add-flow-history, C2). 시간은 흐름 저장 시각 기준."""
    node: str                               # 돈 단계 (documents … assign, engineer_review 등)
    finished_at: datetime
    seconds: float
    changes: list[FlowChange]
    action: str | None                      # 그 단계에서 받은 사람 동작 (submit·approve 등)


class RunFlow(Out):
    """검토 하나의 흐름 기록 (add-flow-history). 읽기 전용."""
    run_id: int
    recorded: bool                          # 흐름 기록이 있는지 (예전 검토는 false)
    stop: str | None                        # 멈춘 자리: 사람 단계 이름, "END", 처리 중간이면 비움
    next_node: str | None                   # 처리 중간에 멈췄으면 다음 단계
    steps: list[FlowStep]


class RunStepTime(Out):
    """실행 기록의 단계 하나 (add-run-log). 끝나지 않은 단계는 seconds가 null."""
    attempt: int                            # 0 = 처음 처리, 1 = 첫 다시 시도
    step: str
    seconds: float | None


class RunLogItem(ReviewFields):
    """실행 기록 한 줄 (add-run-log, NFR-09). 비용은 모델 단가(팀 가정)로 어림한 값."""
    run_id: int
    review_no: str
    engineer_name: str | None
    stage: Stage
    failed_step: str | None
    cancelled: bool
    started_at: datetime
    finished_at: datetime | None
    seconds: float | None
    llm_model: str | None
    dict_version: str
    llm_calls: int
    llm_retries: int
    llm_input_tokens: int
    llm_output_tokens: int
    llm_thinking_tokens: int
    estimated_cost_krw: int | None          # 단가표에 없는 모델이면 null, AI 없이 돌면 0
    cost_assumed: bool                      # 단가가 팀 가정 (CR-06)
    documents: int
    documents_reused: int
    requirements: int
    judgments: int
    explanations_dropped: int               # 근거 대조에서 버린 위험 조건 설명 수
    type_examples: int = 0                  # 사람이 고른 유형 예시를 붙여 물은 줄 수 (C3)
    resumed_from: str | None = None         # 이어서 다시 시도한 단계 (C2). 처음부터면 비움
    documents_reprocessed: int = 0          # 점검 뒤 다시 물은 문서 수 (C1)
    lines_reprocessed: int = 0              # 점검 뒤 다시 물은 줄 수 (update-partial-reprocess)
    explanations_unverified: int            # AI 검증에서 확인 필요로 표시된 설명 수
    retries: int
    steps: list[RunStepTime]


AiFeature = Literal["ANALYSIS", "ASSISTANT", "HANDOFF_ASK", "PRODUCT_SWITCH", "LOSS_EDIT",
                    "REVIEW_ACTION", "BULK_CONFIRM"]


class AiUsageRow(Out):
    """날짜·기능·모델별 AI 사용량 (add-ai-usage-log). ANALYSIS는 분석 실행(review_run) 합."""
    day: date
    feature: AiFeature
    feature_name: str
    model: str | None
    calls: int
    retries: int
    input_tokens: int
    output_tokens: int
    thinking_tokens: int
    estimated_cost_krw: int | None          # 팀 가정 단가. 단가를 모르는 모델이면 null


class AiUsage(Out):
    days: int
    items: list[AiUsageRow]
    total_calls: int
    total_cost_krw: int | None


# ---------------------------------------------------------------------
# 정답지·채점 (add-evaluation, 명세 evaluation)

class AnswerKey(Out):
    """정답지. TYPE = 유형 정답지, REQ = 요구사항 정답지(add-requirement-answer-key).

    made_by가 CLAUDE_DRAFT(Claude 초안)·AUTO(코드 자동)면 사람 확인 전."""
    key_id: int
    key_name: str
    key_kind: Literal["TYPE", "REQ"]
    made_by: Literal["CLAUDE_DRAFT", "HUMAN", "AUTO"]
    doc_name: str | None                # 요구사항 정답지의 대상 문서 이름
    created_at: datetime
    rows: int
    human_checked: int
    ambiguous: int


class EvalRun(Out):
    """채점에 넣을 수 있는 검토 (사람이 확정·수정한 판정 줄이 있음)."""
    run_id: int
    review_no: str
    review_name: str | None
    stage: Stage
    reviewed: int                       # 사람이 확정·수정한 판정 줄 (0이면 요구사항 정답지 채점용)
    reviewer: str | None
    last_reviewed_at: datetime | None


class EvalMetric(Out):
    """지표 하나. 값이 없으면(분모 0) null. 목표가 없으면 passed는 null."""
    code: str
    name: str
    measure: str
    unit: str
    value: float | None
    num: int | None
    den: int | None
    target: float | None
    better: Literal["up", "down"]
    passed: bool | None
    note: str | None


class EvalTypeDetail(Out):
    rows: int
    matched: int
    hit: int
    miss: int
    not_found: int
    ambiguous: int
    ambiguous_hit: int


class EvalRequirementDetail(Out):
    """요구사항 정답지 채점의 자세한 수 (K1·K2·K3·K10)."""
    documents: int
    requirement_rows: int
    found: int
    system_requirements: int
    correct: int
    value_rows: int
    value_hit: int
    risk_rows: int
    risk_found: int


class EvalNotMeasured(Out):
    code: str
    name: str
    note: str


class EvalMetrics(Out):
    items: list[EvalMetric]
    types: EvalTypeDetail | None
    requirements: EvalRequirementDetail | None = None
    not_measured: list[EvalNotMeasured]


class EvalScore(Out):
    """채점 기록 한 줄."""
    score_id: int
    run_ids: list[int]
    key_id: int | None
    key_name: str | None
    key_made_by: Literal["CLAUDE_DRAFT", "HUMAN", "AUTO"] | None
    req_key_id: int | None
    req_key_name: str | None
    req_key_made_by: Literal["CLAUDE_DRAFT", "HUMAN", "AUTO"] | None
    metrics: EvalMetrics
    note: str | None
    code_version: str | None
    scored_by: int | None
    scored_by_name: str | None
    scored_at: datetime


class RuleSuggestion(Out):
    """위험 표현 사전에 추가 제안 (add-rule-suggestion). 위치는 표현이 나온 첫 문장."""
    suggestion_id: int
    expression: str
    note: str | None
    run_id: int
    review_no: str
    requirement_id: int
    status: Literal["PENDING", "ACCEPTED", "DECLINED"]
    suggested_by: int
    suggested_by_name: str
    suggested_at: datetime
    decided_by: int | None
    decided_by_name: str | None
    decided_at: datetime | None
    decision_reason: str | None
    edit_id: int | None
    locations: Locations


class MeaningCandidate(Out):
    """뜻으로 찾은 후보 (add-meaning-search). RISK_SENTENCE = 사전 추가 후보(B5),
    ITEM_LINK = 항목 연결 후보(B3). 후보일 뿐 판정·위험 조건이 아니다."""
    candidate_id: int
    run_id: int
    review_no: str
    kind: Literal["RISK_SENTENCE", "ITEM_LINK"]
    requirement_id: int
    text_raw: str
    near_text: str                      # 가장 가까운 문장·표현
    target: str | None                  # 항목키 또는 가까운 위험 조건 종류
    score: float
    second_target: str | None
    second_score: float | None
    status: Literal["OPEN", "ACCEPTED", "HIDDEN"]
    locations: Locations


class RiskMeaning(Out):
    """위험 조건 탭 사전 추가 후보.

    status: DONE / NO_AI(언어 모델 없음) / SKIPPED(실패) / null(예전 검토)."""
    status: Literal["DONE", "NO_AI", "SKIPPED"] | None
    items: list[MeaningCandidate]


class AssistantEvidence(Out):
    """검토 도우미 근거 줄: 요구사항(R…) 또는 판정(J…). 원문 위치 필수 (CR-02)."""
    ref: str
    kind: Literal["REQUIREMENT", "JUDGMENT"]
    requirement_id: int
    judgment_id: int | None
    text_raw: str
    type_code: str | None
    result: JudgmentResult | None
    item_name: str | None
    req_value_raw: str | None
    product_value_raw: str | None
    locations: Locations


class AssistantSentence(Out):
    """AI가 쓴 답 문장. 근거 번호는 코드가 대조했다 (CR-07)."""
    text: str
    evidence_ids: list[str]


class AssistantStep(Out):
    """찾은 경로 한 단계: 도구와 인자, 찾은 줄 수."""
    tool: Literal["search_requirements", "find_judgments", "get_requirement"]
    words: str | None
    type_code: str | None
    result: str | None
    ref: str | None
    found: int


class AssistantAnswer(Out):
    """검토 도우미 답 (add-review-assistant, FR-17). mode SEARCH = AI 없이 글자로 찾음."""
    mode: Literal["AI", "SEARCH"]
    sentences: list[AssistantSentence]
    evidence: list[AssistantEvidence]
    dropped: int
    steps: list[AssistantStep]
    note: str | None


class PeakCheck(Out):
    """검산 확인 (add-check-calculator). 분석 검산과 같은 규칙, 저장 안 함.

    확인 필요면 계산값이 비어 있다.
    """
    rule_code: str
    factor: float | None
    expected_ka: float | None
    allowed_ka: list[float]
    result: Literal["PASS", "VIOLATION", "NEEDS_REVIEW"]
    reason_code: str | None
