import { useState } from 'react'
import { api, type LogEntry, type RunSummary } from '../api'
import { daysLeft, dday, dueText, num, reviewTitle, stamp } from '../components/format'
import { RESULT_NAMES, RISK_NAMES, STAGE_NAMES, STAGE_TONES, locationText } from '../components/labels'
import { useLoad } from '../components/useLoad'
import { href } from '../shell/router'
import { useSession } from '../shell/useSession'
import { loadCounts, ratioText } from '../components/approval'
import { CheckList } from './CheckList'

// SCR-12 결재 대기 상세 (목업 v4.57 Wait). docs/screens/SCR-12-결재대기.md
// 승인 대기인 검토를 열면 이 화면이 보인다. 엔지니어는 상신 취소, 지정 결재자는 승인·반려, 다른 승인자는 읽기만.
// 다시 알림·열람·전자결재 번호·참조·첨부는 범위 밖이라 없다 (SCR-12_공유.md).

const KIND_CLS: Record<string, string> = { 일탈: 'st c-red', 질의: 'st c-ora', 위험: 'st c-ora' }

type Row = { key: string; kind: string; item: string; req: string; ours: string; loc: string }

async function loadRows(runId: number): Promise<Row[]> {
  const [dev, query, risks] = await Promise.all([
    api.judgments(runId, { result: 'DEVIATION_CANDIDATE', limit: 100 }),
    api.judgments(runId, { result: 'QUERY_CANDIDATE', limit: 100 }),
    api.risks(runId),
  ])
  const judged = [...dev, ...query].filter((j) => j.review_status !== 'REJECTED').map((j) => ({
    key: `j${j.judgment_id}`, kind: j.result === 'DEVIATION_CANDIDATE' ? '일탈' : '질의',
    item: j.item_name ?? j.item_name_raw ?? '—',
    req: [j.req_value_raw, j.unit_raw].filter(Boolean).join(' ') || '—',
    ours: [j.product_value_raw, j.product_value_unit].filter(Boolean).join(' ') || RESULT_NAMES[j.result],
    loc: j.locations[0] ? locationText(j.locations[0]) : '—',
  }))
  const open = risks.filter((r) => r.status !== 'CLOSED_OK').map((r) => ({
    key: `r${r.risk_id}`, kind: '위험', item: RISK_NAMES[r.risk_kind] ?? r.risk_kind,
    req: r.expression ?? r.members[0]?.value_raw ?? '—', ours: r.facts ?? '확인 필요',
    loc: r.members[0]?.locations[0] ? locationText(r.members[0].locations[0]) : '—',
  }))
  return [...judged, ...open]
}

/** 처리 기록 한 줄 (검토 실행 단계 바뀜만) */
function historyLine(l: LogEntry, approverName: (id: unknown) => string): string | null {
  const to = l.after_value?.stage
  if (l.action === 'CONFIRM' && to === 'APPROVAL') return `${l.actor} 결재 상신 → ${approverName(l.after_value?.approver_id)}`
  if (l.action === 'EDIT' && l.reason === '상신 취소') return `${l.actor} 상신 취소`
  if (l.action === 'CONFIRM' && to === 'APPROVED') return `${l.actor} 승인`
  if (l.action === 'REJECT') return `${l.actor} 반려`
  if (l.action === 'EDIT' && to === 'ENGINEER_REVIEW') return `${l.actor} 반려 뒤 다시 확인`
  return null
}

export function WaitView({ run, onChanged, onWithdrawn }: { run: RunSummary; onChanged: () => void; onWithdrawn: () => void }) {
  const { user, users } = useSession()
  const id = run.run_id
  const screen = useLoad(() => api.approval(id), [id])
  const counts = useLoad(() => loadCounts(id), [id])
  const rows = useLoad(() => loadRows(id), [id])
  const docs = useLoad(() => api.documents(id), [id])
  const equipment = useLoad(() => api.equipment(id), [id])
  const log = useLoad(() => api.history(id), [id])
  const waits = useLoad(() => api.runs().then((all) => all.filter((r) => r.stage === 'APPROVAL')), [])
  const [comment, setComment] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const a = screen.data?.approval
  const ratio = screen.data?.review_ratio
  const owner = a?.requested_by ?? '—'
  const appr = a?.approver ?? '—'
  const sent = a ? stamp(a.requested_at) : '—'
  const days = a ? -daysLeft(a.requested_at.slice(0, 10)) : 0
  const overdue = run.due_date ? daysLeft(run.due_date) < 0 : false
  const late = days >= 7 || overdue
  const due = run.due_date ? dday(run.due_date) : null
  const isEngineer = user?.role === 'ENGINEER'
  const isApprover = !!user && user.user_id === a?.approver_id
  const at = waits.data?.findIndex((r) => r.run_id === id) ?? -1
  const prev = at > 0 ? waits.data![at - 1] : null
  const next = at >= 0 && waits.data && at < waits.data.length - 1 ? waits.data[at + 1] : null
  const userName = (uid: unknown) => users.find((u) => u.user_id === uid)?.user_name ?? appr
  const hist = (log.data ?? []).map((l) => ({ l, x: historyLine(l, userName) })).filter((h) => h.x).reverse()
  const c = counts.data
  const sum: [string, string][] = c && ratio ? [
    ['요구사항', num(c.requirements)], ['일탈 후보', String(c.deviations)], ['질의 후보', String(c.queries)],
    ['확인 필요', ratioText(ratio)], ['위험 조건', String(c.risks)], ['손실 환산 가산액', c.loss],
  ] : []
  const products = [...new Set((equipment.data ?? []).map((e) => e.chosen_product ?? e.products?.[0]).filter(Boolean))].join(', ')

  const act = (p: Promise<unknown>, done: () => void) => {
    setBusy(true)
    setError(null)
    p.then(done, (e: Error) => setError(e.message)).finally(() => setBusy(false))
  }
  // 취소되면 검토가 담당자 확인으로 돌아가므로 바로 검토 상세(판정 탭)로 보낸다. 알림은 검토 상세가 띄운다
  const withdraw = () => act(api.withdraw(id, user!.user_id), onWithdrawn)
  const decide = (d: 'APPROVED' | 'REJECTED') => act(api.decide(id, d, comment.trim(), user!.user_id), onChanged)

  let barTitle = `${appr}의 결재를 기다리고 있습니다`
  if (isApprover) barTitle = '결재할 검토입니다'
  const barSub = `상신 후 ${days}일${overdue ? ' · 제출 마감이 지났습니다' : late ? ' · 오래 기다리고 있습니다' : ''}`
    + (!isApprover && user?.role === 'APPROVER' ? ` · 지정된 결재자(${appr})만 결정할 수 있습니다` : '')

  return (
    <main className="main">
      <div className="fid">
        <span>{run.review_no}</span>
        <span className={`st ${STAGE_TONES[run.stage]}`}>{STAGE_NAMES[run.stage]}</span>
        {run.due_date && due && <span>마감 {dueText(run.due_date)} <b className={due.cls}>{due.text}</b></span>}
        <span>상신 {sent}</span><span>기안 {owner}</span><span>결재자 {appr}</span>
      </div>
      <div className="fh">
        <h1>{reviewTitle(run)}</h1>
        <div className="bvnav" style={{ display: 'flex', gap: 6 }}>
          <a className={prev ? '' : 'dis'} href={prev ? href(`/reviews/${prev.run_id}`) : undefined} aria-disabled={!prev}>
            <span className="ms" aria-hidden="true" style={{ fontSize: 18 }}>chevron_left</span>이전 결재 대기</a>
          <a className={next ? '' : 'dis'} href={next ? href(`/reviews/${next.run_id}`) : undefined} aria-disabled={!next}>
            다음 결재 대기<span className="ms" aria-hidden="true" style={{ fontSize: 18 }}>chevron_right</span></a>
        </div>
      </div>

      <div className="fgrid">
        <div style={{ minWidth: 0 }}>
          {a && (
            <div className={'wbar' + (late ? ' late' : '')}>
              <span className="ms" aria-hidden="true">{late ? 'schedule' : 'hourglass_top'}</span>
              <div className="tx"><b>{barTitle}</b><span>{barSub}</span></div>
              <div className="acts">
                {isApprover ? (
                  <>
                    <button type="button" className="bo" disabled={busy || !comment.trim()} onClick={() => decide('REJECTED')}
                      title={comment.trim() ? '' : '반려에는 의견이 필요합니다'}>
                      <span className="ms" aria-hidden="true" style={{ fontSize: 16 }}>block</span>반려</button>
                    <button type="button" className="bp" disabled={busy} onClick={() => decide('APPROVED')}>
                      <span className="ms" aria-hidden="true" style={{ fontSize: 16 }}>check</span>승인</button>
                  </>
                ) : (
                  <button type="button" className="bo" disabled={busy || !isEngineer} onClick={withdraw}
                    title={isEngineer ? '' : '기술 검토 엔지니어만 할 수 있습니다'}>
                    <span className="ms" aria-hidden="true" style={{ fontSize: 16 }}>undo</span>상신 취소</button>
                )}
              </div>
            </div>
          )}
          {error && <p className="aphint" role="alert">{error}</p>}

          {isApprover && (
            <section className="fcard"><h2>결재 의견<span className="note">반려하려면 필수</span></h2>
              <textarea className="fi" rows={3} aria-label="결재 의견" value={comment} onChange={(e) => setComment(e.target.value)}
                placeholder="예: 4,000 A 일탈 사유를 보완할 것" style={{ width: '100%' }} />
            </section>
          )}

          <section className="fcard"><h2>결재 진행</h2>
            <div className="wline">
              <div className="wnode"><span className="r">기안</span><b>{owner}</b><span className="s ok">상신 {sent}</span></div>
              <span className="ms warr" aria-hidden="true">arrow_forward</span>
              <div className="wnode cur"><span className="r">결재</span><b>{appr}</b>
                <span className={'s ' + (late ? 'late' : 'wait')}>결재 대기</span></div>
            </div>
            <div className="wlock"><span className="ms" aria-hidden="true">lock</span>
              <span>결재가 끝날 때까지 판정은 상신한 내용 그대로 잠겨 있습니다. 고쳐야 하면 기안자가 상신을 취소한 뒤 다시 상신합니다.</span></div>
          </section>

          <section className="fcard"><h2>상신한 내용<span className="note">상신 시점 기준</span></h2>
            <div className="wsum">{sum.map(([k, v]) => <div key={k}>{k}<b>{v}</b></div>)}</div>
            <h2 style={{ margin: '18px 0 8px', fontSize: 'var(--fs-body)' }}>상신 전 확인 결과</h2>
            {ratio && <CheckList found={screen.data?.reasons ?? []} ratio={ratio} listed={screen.data?.submission_check?.deviation_listed}
              unread={screen.data?.read_unchecked} compact />}
            {a?.request_comment && <div className="wop">{a.request_comment}<span className="by">상신 의견 · {owner} · {sent}</span></div>}
          </section>

          <section className="fcard"><h2>결재자가 볼 항목<span className="note">일탈 · 질의 · 위험 조건</span></h2>
            <div className="wtw"><table className="wt">
              <thead><tr><th style={{ width: 64 }}>구분</th><th>항목</th><th>요구</th><th>우리 제안 · 판단</th><th>원문 위치</th></tr></thead>
              <tbody>
                {rows.data?.length === 0 && <tr><td colSpan={5} style={{ color: 'var(--c-muted)' }}>일탈·질의·위험 조건이 없습니다.</td></tr>}
                {rows.data?.map((r) => (
                  <tr key={r.key}><td><span className={KIND_CLS[r.kind]}>{r.kind}</span></td><td style={{ fontWeight: 600 }}>{r.item}</td>
                    <td>{r.req}</td><td>{r.ours}</td><td className="loc" style={{ color: 'var(--c-muted)', fontSize: 'var(--fs-xs)' }}>{r.loc}</td></tr>
                ))}
              </tbody>
            </table></div>
          </section>
        </div>

        <aside style={{ minWidth: 0 }}>
          <section className="fcard"><h2>기본 정보</h2>
            <dl className="winfo">
              <dt>고객사</dt><dd>{run.customer_name ?? '—'}</dd>
              <dt>국가</dt><dd>{run.country ?? '—'}</dd>
              <dt>비교 제품</dt><dd>{products || '—'}</dd>
            </dl>
          </section>
          <section className="fcard"><h2>RFP 문서<span className="note">{docs.data?.length ?? 0}개</span></h2>
            <ul className="ffiles">{docs.data?.map((d) => (
              <li key={d.document_id}><span className="ms" aria-hidden="true">description</span><span className="nm">{d.file_name}</span></li>
            ))}</ul>
          </section>
          <section className="fcard"><h2>처리 기록</h2>
            <ul className="ftl">{hist.map(({ l, x }) => (
              <li key={l.log_id} style={{ gridTemplateColumns: '82px 1fr' }}><span className="t">{stamp(l.acted_at)}</span><span>{x}</span></li>
            ))}</ul>
          </section>
        </aside>
      </div>
    </main>
  )
}
