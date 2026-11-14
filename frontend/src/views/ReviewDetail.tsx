import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import { ErrorText } from '../components/common'
import { SummaryBox } from '../components/SummaryBox'
import { useLoad } from '../components/useLoad'
import { useCrumbTail } from '../shell/crumb'
import { usePageCss } from '../shell/pageCss'
import { pathQuery, useHashPath } from '../shell/router'
import { useSession } from '../shell/useSession'
import { useToast } from '../ui'
import { DocumentsDialog } from './DocumentsDialog'
import { AssistantPanel } from './detail/AssistantPanel'
import { DetailBody, DetailTabs } from './detail/DetailBody'
import { MAIN_TABS, MORE_TABS, type DetailTab } from './detail/tabs'
import { useExport } from './detail/ExportOverlay'
import { ProductSeg, type Rejudging } from './detail/ProductSeg'
import { useComplyAll, useHeadCounts, tabCounts } from './detail/headCounts'
import { ActionBar, InfoBox, TitleRow } from './detail/ReviewHead'
import { FailView } from './FailView'
import { ProcessingView } from './ProcessingView'
import { ReviewInfoDialog } from './ReviewInfoDialog'
import { SubmitDialog } from './SubmitDialog'
import { WaitView } from './WaitView'

// SCR-08 검토 상세 (목업 v4.96 Detail, update-detail-header). 제목 줄, 정보 3묶음, 비교 제품, 탭 5개 + 더 보기, 탭 본문, 아래 행동 줄.
// 승인 대기인 검토는 SCR-12 결재 대기 화면(WaitView), 실패는 SCR-11(FailView)로 보인다.

/** 비교 제품을 바꿔 다시 판정하는 동안 화면 전체를 덮고 가운데에 크게 알린다. 막이 클릭을 받아 다른 단추가 눌리지 않는다 (update-rejudge-busy) */
function RejudgeCover({ busy }: { busy: Rejudging }) {
  return (
    <div className="rjcover" role="alertdialog" aria-modal="true" aria-busy="true" aria-labelledby="rj-title">
      <div className="rjbox">
        <span className="rjspin" aria-hidden="true" />
        <b id="rj-title">다시 판정 중…</b>
        <span>{busy.group} · {busy.product} 기준으로 다시 판정하고 있습니다.</span>
        <span className="rjsub">끝나면 판정·손실 환산·제안 포인트가 새로 보입니다. 그동안 다른 단추는 누를 수 없습니다.</span>
      </div>
    </div>
  )
}

export function ReviewDetail({ runId }: { runId: number }) {
  const { data: run, error, reload } = useLoad(() => api.run(runId), [runId])
  const approval = useLoad(() => api.approval(runId), [runId, run?.stage])
  const docs = useLoad(() => api.documents(runId), [runId, run?.stage])
  const { user } = useSession()
  const toast = useToast()
  const [editing, setEditing] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [docsOpen, setDocsOpen] = useState(false)
  const [asking, setAsking] = useState(false)
  const [tab, setTab] = useState<DetailTab>('judge')
  const [tick, setTick] = useState(0)                // 판정을 고치면 머리글 건수와 탭 본문을 다시 센다
  const [version, setVersion] = useState(0)          // 비교 제품을 바꾸거나 문서를 더하면 탭 본문을 새로 불러온다
  const [rejudging, setRejudging] = useState<Rejudging | null>(null)
  const exporter = useExport(runId)
  const fallback = { run_id: runId, stage: 'PROCESSING' } as Parameters<typeof useHeadCounts>[0]
  const head = useHeadCounts(run ?? fallback, tick + version)
  const changed = () => { setTick((t) => t + 1); reload() }
  const comply = useComplyAll(run ?? fallback, head.data ?? null, changed)
  usePageCss(run?.stage === 'APPROVAL' ? 'Wait' : run?.stage === 'FAILED' ? 'Fail' : 'Detail')
  usePageCss(run?.stage === 'APPROVAL' || run?.stage === 'FAILED' ? 'Main' : 'DetailV496')
  useCrumbTail(run?.review_no)
  // 요약 문장 링크 "?tab=log" 등으로 탭을 고른다 (add-screen-summary)
  const qtab = pathQuery(useHashPath()).get('tab')
  const [seenTab, setSeenTab] = useState<string | null>(null)
  if (qtab !== seenTab) {                            // 주소의 탭이 바뀐 그 렌더에서만 고른다
    setSeenTab(qtab)
    if ([...MAIN_TABS, ...MORE_TABS].some(([k]) => k === qtab)) setTab(qtab as DetailTab)
  }
  // 요약 상자: 판정을 고치거나(tick) 제품·문서를 바꾸면(version) 다시 쓴다
  const summary = useCallback(() => api.runSummaryText(runId), [runId, tick, version, run?.stage]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (run?.stage !== 'PROCESSING') return
    const timer = setTimeout(reload, 2000)           // 처리 중이면 단계를 다시 본다
    return () => clearTimeout(timer)
  }, [run, reload])
  if (!run) return <main className="main"><ErrorText error={error} /></main>
  const withdrawn = () => {
    setTab('judge')
    toast.done('상신을 취소했습니다. 판정을 고친 뒤 다시 결재 상신해 주세요.')
    reload()
  }
  if (run.stage === 'APPROVAL') return <WaitView key={run.run_id} run={run} onChanged={reload} onWithdrawn={withdrawn} />
  const latest = approval.data?.approval
  if (run.stage === 'FAILED') return <main className="main"><FailView run={run} approver={latest?.approver ?? null} onChanged={reload} /></main>
  const ready = run.stage !== 'PROCESSING'
  const approver = latest && latest.decision !== null ? latest.approver : null
  // 문서 추가는 담당자 확인 단계의 엔지니어만 (add-document-addendum). 문서 표 창 아래 "문서 추가" 칸을 연다
  const canAdd = run.stage === 'ENGINEER_REVIEW' && user?.role === 'ENGINEER' && docs.data
  const bumped = () => { setVersion((v) => v + 1); reload() }
  return (
    <main className="main">
      <TitleRow run={run} onRefresh={changed} onAddDoc={canAdd ? () => setDocsOpen(true) : null}
        onAsk={ready ? () => setAsking(true) : null} asking={asking} onEdit={() => setEditing(true)} onWord={exporter.start} />
      {ready && <SummaryBox load={summary} label="검토 요약" />}
      <InfoBox run={run} docs={docs.data} approver={approver ?? latest?.approver ?? null} head={head.data ?? null}
        onDocs={() => setDocsOpen(true)} onTab={setTab} onComply={comply.run} complying={comply.busy} />
      {ready && <ProductSeg run={run} onSwitched={bumped} onBusy={setRejudging} />}
      {ready && <DetailTabs tab={tab} onTab={setTab} counts={tabCounts(head.data)} />}
      {ready
        ? <DetailBody key={`${run.stage}-${version}`} run={run} tab={tab} tick={tick} onTab={setTab} onChanged={changed} />
        : <ProcessingView run={run} onChanged={reload} />}
      {ready && <ActionBar run={run} head={head.data ?? null} approver={approver} onSubmit={() => setSubmitting(true)}
        onComply={comply.run} complying={comply.busy} />}
      {asking && <AssistantPanel runId={run.run_id} docs={docs.data ?? []} onClose={() => setAsking(false)} />}
      {docsOpen && docs.data && <DocumentsDialog run={run} docs={docs.data} onClose={() => setDocsOpen(false)} onAdded={bumped} />}
      {editing && <ReviewInfoDialog run={run} onClose={() => setEditing(false)} onSaved={() => { setEditing(false); reload() }} />}
      {submitting && <SubmitDialog run={run} onClose={() => setSubmitting(false)} onDone={() => { setSubmitting(false); reload() }} />}
      {rejudging && <RejudgeCover busy={rejudging} />}
      {exporter.view}
    </main>
  )
}
