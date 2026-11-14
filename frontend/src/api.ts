// 백엔드 API (/api, Vite 프록시). 응답 타입은 백엔드 응답 모델에서 만든다 (api.gen.ts, `npm run gen:api`).
import type {
  ActionResult, TypeEditResult, ApprovalScreen, AssignmentStatus, BulkResult, CompareTargets, CostSummary, PastCompare, BusinessDetail, BusinessList, BusinessLog,
  DecisionResult, DocumentChoice, DocumentPreview, HandoffResult, SalesHandoff,
  LossResult, ProductSwitch, RuleEdit,
  RunFlow, RunLogItem, RunSummary, ScreenSummary, SendResult, StageResult, SubmitResult,
  AnswerKey, EvalRun, EvalScore, RuleSuggestion, AssistantAnswer, MeaningCandidate, RiskMeaning, AiUsage, PeakCheck,
} from './api.gen'

export type {
  AiUsage, AiUsageRow, PeakCheck,
  ApprovalScreen, Assignment, BusinessDetail, CommercialImpact, CompareRow, CompareTarget, CompareTargets, PastCompare, CostCondition, CostSummary, BusinessEvent, BusinessList, BusinessListItem, BusinessLog, BusinessPerson,
  BusinessRange, CompareRule, Criterion, Datasheet, DatasheetInfo, DatasheetRow, DocKindRule,
  DocumentChoice, DocumentLines, DocumentPreview, EngineeringCheck,
  Equipment, Health, ItemKey, Judgment, JudgmentCounts, Location, LogEntry, Loss, MyTasks, OutputItem, Product,
  ProductDetail, ProductFamily, ProductUse, Proposal, ReadCheck, Requirement, ReviewCard, Risk, RiskExpression, RuleEdit, RunDocument,
  AnswerKey, EvalMetric, EvalRun, EvalScore, AssistantAnswer, AssistantEvidence, Revision, FlowStep, RunFlow, RunListItem, RunLogItem, RunSummary, RuleSuggestion, ScreenSummary, MeaningCandidate, RiskMeaning, SalesHandoff, SubmissionCheck, Tbe, TbeRow, User, Warranty,
} from './api.gen'
import type {
  CompareRule, DatasheetInfo, Datasheet, DocKindRule, EngineeringCheck, Equipment, Health, ItemKey, Judgment, JudgmentCounts,
  DocumentLines, LogEntry, Loss, MyTasks, OutputItem, Product, ProductDetail, ProductFamily, Proposal, ReadCheck, Requirement,
  Risk, RiskExpression, RunDocument, RunListItem, SubmissionCheck, Tbe, User, Warranty, Assignment,
} from './api.gen'

export type Stage = RunSummary['stage']

/** 사람이 넣는 검토 정보 (add-review-info). 비어 있으면 null */
export type ReviewInfo = Pick<RunSummary, 'project_name' | 'review_name' | 'customer_name' | 'country' | 'due_date'
  | 'engineer_id'>

export type JudgmentQuery = {
  result?: string; group?: string; type_code?: string; q?: string; unconfirmed?: boolean; order?: 'priority'
  past?: 'differs'   // 지난 사람 판정과 다른 줄만 (add-review-memory)
  revised?: boolean  // 마지막 문서 추가 개정에서 바뀌거나 추가된 줄만 (add-revision-notice)
  offset?: number; limit?: number
}

/** 규칙 사전 이름과 고칠 값 (add-rule-editing). 값 칸은 사전마다 다르다 */
export type RuleDictionary = RuleEdit['dictionary']
export type RuleValue = Record<string, string | number | boolean | string[] | null>

export type TbeQuery = { include: 'all' | 'confirmed'; lang: 'en' | 'ko' | 'both'; base: 'now' | 'v1' }

export type ActionBody = {
  target: string
  target_id: number
  action: string
  value?: Record<string, unknown>
  reason?: string
  actor_id?: number
}

async function send(path: string, init?: RequestInit): Promise<Response> {
  const res = await fetch(`/api${path}`, init)
  if (!res.ok) {
    let message = `API ${res.status}`
    try {
      const body = await res.json()
      if (typeof body.detail === 'string') message = body.detail
    } catch {
      // 본문이 JSON이 아니면 상태 코드만 보여 준다
    }
    throw new Error(message)
  }
  return res
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  return (await send(path, init)).json()
}

/** 내려받을 파일: 이름(Content-Disposition filename*)과 내용 */
async function file(path: string, init?: RequestInit): Promise<{ name: string; blob: Blob }> {
  const res = await send(path, init)
  const m = /filename\*=UTF-8''([^;]+)/.exec(res.headers.get('Content-Disposition') ?? '')
  return { name: m ? decodeURIComponent(m[1]) : 'download', blob: await res.blob() }
}

/** 나눠 받는 목록과 거른 전체 개수(X-Total-Count 머리글). */
export type Page<T> = { items: T[]; total: number }

async function page<T>(path: string): Promise<Page<T>> {
  const res = await send(path)
  const items: T[] = await res.json()
  return { items, total: Number(res.headers.get('X-Total-Count') ?? items.length) }
}

/** 검토 시작 때 함께 보내는 검토 정보. 빈 칸은 보내지 않는다.
 * 사업 연결(add-project-status): business_id(진행 중인 사업에 추가) 또는 new_business_name(새 사업 만들기) */
export type StartInfo = Partial<Omit<ReviewInfo, 'engineer_id'>> & {
  engineer_id?: number | null; actor_id?: number | null; business_id?: number | null; new_business_name?: string
}

/** 사업 정보 (add-project-status). 보낸 칸만 바꾸고 빈 문자열은 비우기 */
export type BusinessInfo = Partial<Record<'business_name' | 'customer_name' | 'country' | 'tender_no' | 'order_mode'
  | 'due_date', string | null>> & { sales_id?: number | null }

/** 사업 번호 PJ-2026-003 → 3 (화면 주소 `#/projects/PJ-2026-003`) */
export function businessIdOf(no: string): number | null {
  const m = /^PJ-\d+-(\d+)$/.exec(no) ?? /^(\d+)$/.exec(no)
  return m ? Number(m[1]) : null
}

function filled(info: StartInfo): Record<string, string | number> {
  const out: Record<string, string | number> = {}
  Object.entries(info).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') out[k] = v
  })
  return out
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const api = {
  health: () => call<Health>('/health'),
  users: () => call<User[]>('/users'),
  runs: (limit = 200) => call<RunListItem[]>(`/runs?limit=${limit}`),
  library: () => call<string[]>('/library'),
  /** 사람이 정한 문서 분류(choices)는 파일 이름마다 */
  startLibrary: (files: string[], info: StartInfo = {}, choices: Record<string, DocumentChoice> = {}) =>
    call<RunSummary>('/runs/library', json('POST', { files, ...filled(info), choices })),
  /** onProgress가 있으면 보낸 바이트를 알린다 (update-register-progress, fetch는 업로드 진행을 주지 않아 XMLHttpRequest) */
  upload: (files: File[], info: StartInfo = {}, choices: Record<string, DocumentChoice> = {},
    onProgress?: (sent: number, total: number) => void) => {
    const form = new FormData()
    files.forEach((f) => form.append('files', f))
    Object.entries(filled(info)).forEach(([k, v]) => form.append(k, String(v)))
    if (Object.keys(choices).length) form.append('choices', JSON.stringify(choices))
    if (!onProgress) return call<RunSummary>('/runs', { method: 'POST', body: form })
    return new Promise<RunSummary>((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      xhr.open('POST', '/api/runs')
      xhr.upload.onprogress = (e) => { if (e.lengthComputable) onProgress(e.loaded, e.total) }
      xhr.onerror = () => reject(new Error('서버에 연결하지 못했습니다'))
      xhr.onload = () => {
        let body: unknown = null
        try { body = JSON.parse(xhr.responseText) } catch { /* 본문이 JSON이 아니면 상태 코드만 */ }
        if (xhr.status >= 200 && xhr.status < 300) return resolve(body as RunSummary)
        const detail = (body as { detail?: unknown } | null)?.detail
        reject(new Error(typeof detail === 'string' ? detail : `API ${xhr.status}`))   // send()와 같은 오류 문장
      }
      xhr.send(form)
    })
  },
  /** 분석 전 분류 추천 (규칙만, 저장 안 함) */
  previewLibrary: (files: string[]) => call<DocumentPreview[]>('/runs/library/preview', json('POST', { files })),
  previewUpload: (files: File[]) => {
    const form = new FormData()
    files.forEach((f) => form.append('files', f))
    return call<DocumentPreview[]>('/runs/preview', { method: 'POST', body: form })
  },
  /** 담당자 확인 단계 검토에 문서를 더해 다시 분석 (add-document-addendum, 엔지니어만) */
  addDocuments: (id: number, files: File[], choices: Record<string, DocumentChoice>, actor_id: number | null) => {
    const form = new FormData()
    files.forEach((f) => form.append('files', f))
    if (Object.keys(choices).length) form.append('choices', JSON.stringify(choices))
    if (actor_id !== null) form.append('actor_id', String(actor_id))
    return call<RunSummary>(`/runs/${id}/documents`, { method: 'POST', body: form })
  },
  /** 지난 RFP 비교 (add-past-compare): 같은 고객사의 지난 검토와 달라진 요구 */
  compareTargets: (id: number) => call<CompareTargets>(`/runs/${id}/compare`),
  compare: (id: number, otherId: number) => call<PastCompare>(`/runs/${id}/compare/${otherId}`),
  /** 보낸 칸만 바꾼다. 빈 문자열은 비우기 */
  updateInfo: (id: number, info: Partial<Record<keyof ReviewInfo, string | number | null>>, actor_id: number | null) =>
    call<RunSummary>(`/runs/${id}/info`, json('PUT', { ...info, actor_id })),
  judgmentPage: (id: number, params: JudgmentQuery) => page<Judgment>(`/runs/${id}/judgments?${query(params)}`),
  judgmentCounts: (id: number) => call<JudgmentCounts>(`/runs/${id}/judgment-counts`),
  /** 요약 상자 문장 (add-screen-summary): 검토 상세, 홈 */
  runSummaryText: (id: number) => call<ScreenSummary>(`/runs/${id}/summary`),
  homeSummary: (userId: number | null) => call<ScreenSummary>(`/home/summary${userId === null ? '' : `?user_id=${userId}`}`),
  run: (id: number) => call<RunSummary>(`/runs/${id}`),
  documents: (id: number) => call<RunDocument[]>(`/runs/${id}/documents`),
  /** 원문 줄 범위 (최대 40줄, add-judgment-view). partial이면 파일이 없어 저장된 줄만 */
  documentLines: (id: number, fileNo: number, from: number, to: number) =>
    call<DocumentLines>(`/runs/${id}/documents/${fileNo}/lines?from=${from}&to=${to}`),
  requirements: (id: number, params: { type_code?: string; offset?: number; limit?: number }) =>
    call<Requirement[]>(`/runs/${id}/requirements?${query(params)}`),
  requirement: (reqId: number, runId: number) => call<Requirement>(`/requirements/${reqId}?run_id=${runId}`),
  risks: (id: number) => call<Risk[]>(`/runs/${id}/risks`),
  judgments: (id: number, params: { result?: string; group?: string; offset?: number; limit?: number }) =>
    call<Judgment[]>(`/runs/${id}/judgments?${query(params)}`),
  equipment: (id: number) => call<Equipment[]>(`/runs/${id}/equipment`),
  chooseProduct: (id: number, group: string, product_code: string | null) =>
    call<ProductSwitch>(`/runs/${id}/equipment/${encodeURIComponent(group)}/product`,
      json('PUT', { product_code })),
  warranty: (id: number, params: { status?: string; offset?: number; limit?: number }) =>
    call<Warranty[]>(`/runs/${id}/warranty?${query(params)}`),
  warrantyPage: (id: number, params: { status?: string; offset?: number; limit?: number }) =>
    page<Warranty>(`/runs/${id}/warranty?${query(params)}`),
  losses: (id: number) => call<Loss[]>(`/runs/${id}/losses`),
  checks: (id: number) => call<EngineeringCheck[]>(`/runs/${id}/checks`),
  updateLoss: (id: number, lossId: number, values: Record<string, number | null>) =>
    call<LossResult>(`/runs/${id}/losses/${lossId}`, json('PUT', values)),
  outputs: (id: number) => call<OutputItem[]>(`/runs/${id}/outputs`),
  /** 상업 조건 탭 (FR-16): 비용 조건 요약과 기술 판단에서 생긴 상업 영향 */
  costConditions: (id: number) => call<CostSummary>(`/runs/${id}/cost-conditions`),
  submissionCheck: (id: number) => call<SubmissionCheck>(`/runs/${id}/submission-check`),
  proposals: (id: number) => call<Proposal[]>(`/runs/${id}/proposals`),
  datasheets: (id: number) => call<DatasheetInfo[]>(`/runs/${id}/datasheets`),
  datasheet: (id: number, tableId: number) => call<Datasheet>(`/runs/${id}/datasheet?table_id=${tableId}`),
  exportDatasheet: (id: number, tableId: number) => file(`/runs/${id}/datasheet/export?table_id=${tableId}`),
  tbe: (id: number, q: TbeQuery) => call<Tbe>(`/runs/${id}/tbe?${query(q)}`),
  exportTbe: (id: number, q: TbeQuery) => file(`/runs/${id}/tbe/export?${query(q)}`),
  exportOutputs: (id: number, list_kind: 'DEVIATION' | 'QUERY') => file(`/runs/${id}/outputs/export?list_kind=${list_kind}`),
  bulkConfirm: (id: number, ids: number[], actor_id: number) =>
    call<BulkResult>(`/runs/${id}/actions/bulk`, json('POST', { target: 'judgment', ids, action: 'CONFIRM', actor_id })),
  act: (id: number, body: ActionBody) =>
    call<ActionResult>(`/runs/${id}/actions`, json('POST', body)),
  // 사람 유형 고치기 (add-type-examples). NONE은 미분류
  setType: (id: number, reqId: number, type_code: string, reason: string | null, actor_id: number) =>
    call<TypeEditResult>(`/runs/${id}/requirements/${reqId}/type`, json('POST', { type_code, reason, actor_id })),
  history: (id: number) => call<LogEntry[]>(`/runs/${id}/history`),
  approval: (id: number) => call<ApprovalScreen>(`/runs/${id}/approval`),
  readChecks: (id: number) => call<ReadCheck[]>(`/runs/${id}/read-checks`),
  checkRead: (id: number, key: string, actor_id: number) =>
    call<ReadCheck>(`/runs/${id}/read-checks/${encodeURIComponent(key)}`, json('POST', { actor_id })),
  uncheckRead: (id: number, key: string, actor_id: number) =>
    call<ReadCheck>(`/runs/${id}/read-checks/${encodeURIComponent(key)}?actor_id=${actor_id}`, { method: 'DELETE' }),
  /** 결재 상신: 결재자와 상신 의견은 필수 */
  submit: (id: number, approver_id: number, comment: string, actor_id: number) =>
    call<SubmitResult>(`/runs/${id}/finish-review`, json('POST', { approver_id, comment, actor_id })),
  withdraw: (id: number, actor_id: number) => call<StageResult>(`/runs/${id}/withdraw`, json('POST', { actor_id })),
  rewind: (id: number, step: string, reason: string, actor_id: number) =>
    call<RunSummary>(`/runs/${id}/rewind`, json('POST', { step, reason, actor_id })),
  runLog: () => call<RunLogItem[]>('/run-log'),
  /** 검산 확인 (add-check-calculator): 분석 검산과 같은 규칙의 참고 계산, 저장 안 함 */
  peakCheck: (ik_ka: number, frequency_hz: number, peak_ka: number) =>
    call<PeakCheck>(`/engineering/peak-check?ik_ka=${ik_ka}&frequency_hz=${frequency_hz}&peak_ka=${peak_ka}`),
  /** 날짜·기능별 AI 사용량, 분석 실행 포함 (add-ai-usage-log). 비용은 팀 가정 단가 */
  aiUsage: (days: number) => call<AiUsage>(`/ai-usage?days=${days}`),
  runFlow: (id: number) => call<RunFlow>(`/runs/${id}/flow`),
  // 정답지·채점 (add-evaluation). 정답지 넣기는 명령 `rfp-db load-answer-key`
  evalKeys: () => call<AnswerKey[]>('/eval/keys'),
  evalRuns: () => call<EvalRun[]>('/eval/runs'),
  evalScores: () => call<EvalScore[]>('/eval/scores'),
  // key_id 유형 정답지(K13), req_key_id 요구사항 정답지(K1·K2·K3·K10, add-requirement-answer-key)
  score: (run_ids: number[], key_id: number | null, note: string, actor_id: number | null, req_key_id: number | null = null) =>
    call<EvalScore>('/eval/scores', json('POST', { run_ids, key_id, req_key_id, note, actor_id })),
  // 처리 중 취소, 실패·취소한 검토 다시 시도 (add-run-control)
  cancelRun: (id: number, actor_id: number | null) => call<RunSummary>(`/runs/${id}/cancel`, json('POST', { actor_id })),
  retryRun: (id: number, actor_id: number | null) => call<RunSummary>(`/runs/${id}/retry`, json('POST', { actor_id })),
  decide: (id: number, decision: string, comment: string, actor_id: number) =>
    call<DecisionResult>(`/runs/${id}/approval`, json('POST', { decision, comment, actor_id })),
  tasks: (user_id: number) => call<MyTasks>(`/tasks?user_id=${user_id}`),
  products: (params: { family?: string; q?: string; offset?: number; limit?: number; cards?: 'false' }) => page<Product>(`/products?${query(params)}`),
  /** 제품표 엑셀 (add-product-export): 목록과 같은 거르기 */
  exportProducts: (params: { family?: string; q?: string; cards?: 'false' }) => file(`/products/export?${query(params)}`),
  productFamilies: () => call<ProductFamily[]>('/products/families'),
  product: (code: string) => call<ProductDetail>(`/products/${encodeURIComponent(code)}`),
  compareRules: () => call<CompareRule[]>('/rules/compare'),
  ruleItems: () => call<ItemKey[]>('/rules/items'),
  riskExpressions: () => call<RiskExpression[]>('/rules/risk-expressions'),
  docKindRules: () => call<DocKindRule[]>('/rules/doc-kinds'),
  ruleEdits: (dictionary?: RuleDictionary) => call<RuleEdit[]>(`/rules/edits${dictionary ? `?dictionary=${dictionary}` : ''}`),
  addRule: (dictionary: RuleDictionary, value: RuleValue, reason: string, actor_id: number) =>
    call<RuleEdit>(`/rules/${dictionary}`, json('POST', { value, reason, actor_id })),
  updateRule: (dictionary: RuleDictionary, id: string, value: RuleValue, reason: string, actor_id: number) =>
    call<RuleEdit>(`/rules/${dictionary}/${encodeURIComponent(id)}`, json('PUT', { value, reason, actor_id })),
  deleteRule: (dictionary: RuleDictionary, id: string, reason: string, actor_id: number) =>
    call<RuleEdit>(`/rules/${dictionary}/${encodeURIComponent(id)}`, json('DELETE', { reason, actor_id })),
  /** 검토 도우미: 읽기 도구만 쓰는 AI에 묻기 (add-review-assistant) */
  ask: (runId: number, question: string) => call<AssistantAnswer>(`/runs/${runId}/assistant`, json('POST', { question })),
  /** 위험 표현 사전에 추가 제안 (add-rule-suggestion) */
  runSuggestions: (runId: number) => call<RuleSuggestion[]>(`/runs/${runId}/rule-suggestions`),
  suggestRule: (runId: number, expression: string, note: string, actor_id: number) =>
    call<RuleSuggestion>(`/runs/${runId}/rule-suggestions`, json('POST', { expression, note, actor_id })),
  ruleSuggestions: () => call<RuleSuggestion[]>('/rule-suggestions'),
  // 뜻으로 찾은 후보 (add-meaning-search): 사전 추가 후보(위험 조건 탭), 항목 연결 후보(판정 규칙 화면)
  riskMeaning: (runId: number) => call<RiskMeaning>(`/runs/${runId}/meaning-candidates`),
  itemCandidates: () => call<MeaningCandidate[]>('/item-candidates'),
  acceptItem: (id: number, actor_id: number) => call<RuleEdit>(`/item-candidates/${id}/accept`, json('POST', { actor_id })),
  hideItem: (id: number, actor_id: number) => send(`/item-candidates/${id}/hide`, json('POST', { actor_id })).then(() => undefined),
  acceptSuggestion: (id: number, value: RuleValue, reason: string, actor_id: number) =>
    call<RuleSuggestion>(`/rule-suggestions/${id}/accept`, json('POST', { value, reason, actor_id })),
  declineSuggestion: (id: number, reason: string, actor_id: number) =>
    call<RuleSuggestion>(`/rule-suggestions/${id}/decline`, json('POST', { reason, actor_id })),
  /** role을 빼면 세 부서 요청 모두 (update-todo-search) */
  assignments: (role?: string) => call<Assignment[]>(role ? `/assignments?role=${role}` : '/assignments'),
  /** 화면이 거른 협조 요청을 엑셀로 (SCR-13 내보내기) */
  exportAssignments: (role: string | null, assignment_ids: number[]) =>
    file('/assignments/export', json('POST', { role, assignment_ids })),
  /** 엔지니어가 회신 받음을 기록하거나 되돌린다 (메일 보냄 ↔ 회신 받음) */
  setTaskStatus: (assignmentId: number, status: 'DOING' | 'DONE', actor_id: number, reply_note?: string) =>
    call<AssignmentStatus>(`/assignments/${assignmentId}`, json('PUT', { status, actor_id, reply_note })),
  /** 협조 요청 메일 보내기·다시 보내기 (판정 없는 요청, 발송 실패·주소 없음) */
  sendRequests: (runId: number, assignment_ids: number[], actor_id: number, resend = false) =>
    call<SendResult>(`/runs/${runId}/assignments/send`, json('POST', { assignment_ids, actor_id, resend })),
  /** 영업 인계 (add-submission-package): 데이터시트 한 장, 결재 승인 뒤 인계 패키지 */
  handoffDatasheet: (runId: number, table_id: number, actor_id: number) =>
    call<HandoffResult>(`/runs/${runId}/datasheet/handoff`, json('POST', { table_id, actor_id })),
  handoffPackage: (runId: number, actor_id: number) =>
    call<HandoffResult>(`/runs/${runId}/package/handoff`, json('POST', { actor_id })),
  downloadPackage: (runId: number) => file(`/runs/${runId}/package`),
  handoffs: (runId: number) => call<SalesHandoff[]>(`/runs/${runId}/handoffs`),
  reopen: (id: number, actor_id: number) => call<StageResult>(`/runs/${id}/reopen`, json('POST', { actor_id })),
  businesses: (user_id: number | null, scope: 'mine' | 'all') =>
    call<BusinessList>(`/businesses?${query({ user_id: user_id ?? undefined, scope })}`),
  business: (id: number, user_id: number | null) =>
    call<BusinessDetail>(`/businesses/${id}${user_id != null ? `?user_id=${user_id}` : ''}`),
  createBusiness: (info: BusinessInfo, actor_id: number | null) =>
    call<BusinessDetail>('/businesses', json('POST', { ...info, actor_id })),
  updateBusiness: (id: number, info: BusinessInfo, actor_id: number | null) =>
    call<BusinessDetail>(`/businesses/${id}`, json('PUT', { ...info, actor_id })),
  markSubmitted: (id: number, actor_id: number | null) =>
    call<BusinessDetail>(`/businesses/${id}/submitted`, json('POST', { actor_id })),
  unmarkSubmitted: (id: number, actor_id: number | null) =>
    call<BusinessDetail>(`/businesses/${id}/submitted${actor_id != null ? `?actor_id=${actor_id}` : ''}`, { method: 'DELETE' }),
  businessHistory: (id: number) => call<BusinessLog[]>(`/businesses/${id}/history`),
  linkBusiness: (runId: number, business_id: number | null, actor_id: number | null) =>
    call<RunSummary>(`/runs/${runId}/business`, json('PUT', { business_id, actor_id })),
}

function query(params: Record<string, string | number | boolean | undefined>): string {
  const q = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== '' && v !== false) q.set(k, String(v))
  })
  return q.toString()
}
