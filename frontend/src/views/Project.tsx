import { useState } from 'react'
import { api, type BusinessDetail } from '../api'
import {
  BUSINESS_ROLE_NAMES, EVENT_NAMES, PART_NAMES, RANGE_NAMES, RANGE_TONES, ddText, rangeGo,
} from '../components/business'
import { DOC_KIND_NAMES, ROLE_NAMES } from '../components/labels'
import { dueText, isoDay } from '../components/format'
import { useLoad, useRepeat } from '../components/useLoad'
import { EXAMPLE_PROJECTS } from '../examples/SCR-04'
import { usePageCss } from '../shell/pageCss'
import { href } from '../shell/router'
import { useSession } from '../shell/useSession'
import { ExampleBand } from './detail/ExampleTab'
import { PackageActions } from '../components/PackageActions'
import { Modal } from '../ui'
import { BusinessDialog } from './BusinessDialog'

// SCR-05 사업 상세 (목업 v4.57 Project). docs/screens/SCR-05-사업상세.md
// 개요(범위 카드)·담당자·일정·문서는 연결된 검토에서 모은 실제 데이터 (add-project-status).
// 지난 이력(입찰 이력)은 범위 밖이라 예시로 남긴다. 고객 측 창구·접속 상태는 만들지 않았다 (SCR-05_공유.md).
// v4.96: "인계 패키지 보기" 창 — 승인된 검토마다 내려받기·영업에 넘기기 (update-home-projects design.md 6).

type Tab = 'ov' | 'ppl' | 'sch' | 'doc' | 'his'
const TABS: [Tab, string][] = [['ov', '개요'], ['ppl', '담당자'], ['sch', '일정'], ['doc', '문서'], ['his', '지난 이력']]
// 지난 이력 예시 (입찰 이력 예시와 같은 이름)
const EXAMPLE_HISTORY = EXAMPLE_PROJECTS[0].hist

export function Project({ businessId }: { businessId: number }) {
  usePageCss('Project')
  usePageCss('ProjectV496')
  const { user } = useSession()
  const [tab, setTab] = useState<Tab>('ov')
  const [editing, setEditing] = useState(false)
  const [pkg, setPkg] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [today] = useState(() => isoDay(new Date()))
  const load = useLoad(() => api.business(businessId, user?.user_id ?? null), [businessId, user?.user_id])
  useRepeat(!!load.data?.ranges.some((r) => r.state === 'an'), load.reload)
  const p = load.data
  if (load.error) return <main className="main"><div className="sh-empty" role="alert">사업을 불러오지 못했습니다: {load.error}</div></main>
  if (!p) return <main className="main"><div className="sh-empty">불러오는 중…</div></main>

  const submitted = p.submitted_at !== null
  const allApproved = p.ranges.length > 0 && p.ranges.every((r) => r.stage === 'APPROVED')
  const approved = p.ranges.filter((r) => r.stage === 'APPROVED')
  const pkgLock = approved.length ? null : '결재가 승인된 검토가 없습니다'
  const next = p.schedule.find((e) => e.day >= today && (e.kind === 'DUE' || e.kind === 'RUN_DUE'))
  const ddCls = submitted || p.days_left == null ? '' : p.days_left <= 3 ? 'neg' : p.days_left <= 7 ? 'crit' : ''
  const toggleSubmitted = () => {
    setBusy(true)
    setError(null)
    const call = submitted ? api.unmarkSubmitted(p.business_id, user?.user_id ?? null) : api.markSubmitted(p.business_id, user?.user_id ?? null)
    call.then(load.reload, (e: Error) => setError(e.message)).finally(() => setBusy(false))
  }

  return (
    <main className="main">
      <div className="pd-top"><span className="mono">{p.business_no}</span><span>고객 입찰 번호 {p.tender_no ?? '—'}</span>
        <span className={submitted ? 'st c-green' : 'st c-blue'}>{submitted ? '제출 완료' : '진행 중'}</span></div>
      <div className="ttl" style={{ marginTop: 6 }}><h1>{p.business_name}</h1>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <span className="hpkw" title={pkgLock ?? undefined}>
            <button type="button" className="bo" disabled={!!pkgLock} onClick={() => setPkg(true)} aria-describedby={pkgLock ? 'pkgLock' : undefined}>
              <span className="ms" aria-hidden="true" style={{ fontSize: 'var(--ic-s)' }}>inventory_2</span>인계 패키지 보기</button>
            {pkgLock && <span id="pkgLock" className="sr">{pkgLock}</span>}</span>
          <a className="bo" href={href('/projects')}><span className="ms" aria-hidden="true" style={{ fontSize: 'var(--ic-s)' }}>list</span>사업 목록</a>
          <button type="button" className="bo" onClick={() => setEditing(true)}><span className="ms" aria-hidden="true" style={{ fontSize: 'var(--ic-s)' }}>edit</span>사업 정보 고치기</button>
          <button type="button" className="bo" disabled={busy || (!submitted && !allApproved)} onClick={toggleSubmitted}
            title={!submitted && !allApproved ? '연결된 검토가 모두 승인되어야 표시할 수 있습니다' : undefined}>
            <span className="ms" aria-hidden="true" style={{ fontSize: 'var(--ic-s)' }}>{submitted ? 'undo' : 'task_alt'}</span>
            {submitted ? '제출 완료 취소' : '제출 완료로 표시'}</button>
          {!submitted && <a className="bp" href={href(`/register/business/${p.business_id}`)}><span className="ms" aria-hidden="true" style={{ fontSize: 'var(--ic-s)' }}>add</span>이 사업에 RFP 등록</a>}
        </div>
      </div>
      {!submitted && !allApproved && (
        <p className="sh-mut" style={{ margin: '4px 0 0' }}>연결된 검토가 모두 승인되어야 제출 완료로 표시할 수 있습니다.</p>
      )}
      {error && <p className="c-red" role="alert" style={{ margin: '4px 0 0' }}>{error}</p>}
      <dl className="pd-info">
        <div><dt>사업명 (검토명 앞부분)</dt><dd>{p.business_name}</dd></div>
        <div><dt>고객사 · 국가</dt><dd>{[p.customer_name, p.country].filter(Boolean).join(' · ') || '—'}</dd></div>
        <div><dt>발주 방식</dt><dd>{p.order_mode ?? '—'}</dd></div>
        <div><dt>제출 마감</dt><dd><b className={ddCls}>{ddText(p)}</b> {p.due_date ? dueText(p.due_date) : ''}
          {p.due_date && !p.business_due_date && <span className="sh-mut"> (검토 마감)</span>}</dd></div>
        <div><dt>다음 일정</dt><dd>{next ? `${EVENT_NAMES[next.kind]} · ${dueText(next.day)}` : '—'}</dd></div>
        <div><dt>내 역할</dt><dd>{p.my_role ? BUSINESS_ROLE_NAMES[p.my_role] : '—'}</dd></div>
      </dl>
      <div className="pgtabs" role="tablist" style={{ marginTop: 24 }}>
        {TABS.map(([k, label]) => (
          <button key={k} type="button" role="tab" className={tab === k ? 'on' : ''} aria-selected={tab === k} onClick={() => setTab(k)}>
            {label}{k === 'ov' ? ` (${p.ranges.length})` : ''}</button>
        ))}
      </div>

      {tab === 'ov' && <Overview p={p} />}
      {tab === 'ppl' && <People p={p} me={user?.user_id ?? null} />}
      {tab === 'sch' && (
        p.schedule.length === 0 ? <div className="sh-empty">일정이 없습니다.</div> : (
          <ol className="ptl">{p.schedule.map((e) => {
            const st = e.day < today ? 'done' : e === next ? 'next' : 'later'
            return (
              <li key={`${e.day}-${e.kind}-${e.run_id}`} className={st}><span className="tl-dot" /><span className="mono tl-d">{dueText(e.day)}</span>
                <b>{EVENT_NAMES[e.kind]}{e.review_no ? ` · ${e.review_no}` : ''}</b>
                <span className={st === 'next' ? 'st c-blue' : 'sh-mut'}>{st === 'done' ? '지남' : ''}</span></li>
            )
          })}</ol>
        )
      )}
      {tab === 'doc' && (
        <div className="sh-box">
          <div className="dc-tr sh-th"><span>문서</span><span>종류</span><span>검토 번호</span><span>영향 범위</span></div>
          {p.documents.length === 0 && <div className="sh-empty">연결된 검토의 문서가 없습니다.</div>}
          {p.documents.map((d) => (
            <a key={`${d.run_id}-${d.file_name}`} className="dc-tr pp-row pl-link" href={href(`/reviews/${d.run_id}`)}>
              <span className="pd-own"><span className="ms" aria-hidden="true" style={{ color: 'var(--c-muted)' }}>description</span><span className="ell">{d.file_name}</span></span>
              <span><span className={d.bundle === 'A' || d.bundle === 'B' ? 'st c-blue' : 'st c-grey'}>{DOC_KIND_NAMES[d.doc_kind] ?? d.doc_kind}</span></span>
              <span className="mono sh-mut">{d.review_no}</span><span className="sh-mut">{d.review_name ?? '—'}</span></a>
          ))}
        </div>
      )}
      {tab === 'his' && (
        <>
          <ExampleBand />
          <p className="sh-mut" style={{ margin: '0 0 10px' }}>같은 고객의 지난 입찰입니다.</p>
          <div className="sh-box">
            {EXAMPLE_HISTORY.map(([bid, name, md, y, res, cls]) => (
              <a key={bid} className="hs-tr pp-row pl-link" href={href(`/bids/${bid}`)}><span className="mono sh-mut">{bid}</span><b>{name}</b><span className="mono sh-mut">{y}-{md}</span>
                <span><span className={cls}>{res}</span></span><span className="ms" aria-hidden="true" style={{ color: 'var(--c-disabled)' }}>chevron_right</span></a>
            ))}
          </div>
        </>
      )}
      {pkg && (
        <Modal title="인계 패키지" onClose={() => setPkg(false)} width={640}>
          <p className="sh-mut" style={{ margin: 0 }}>결재가 승인된 검토의 일탈 목록·질의서 초안, TBE 준수표, 데이터시트를 zip 하나로 묶어 영업에 넘깁니다.</p>
          {approved.map((r) => (
            <PackageActions key={r.run_id} runId={r.run_id}
              label={<><b className="mono">{r.review_no}</b> · <a href={href(`/reviews/${r.run_id}`)}>{r.review_name ?? '설비 범위 없음'}</a></>} />
          ))}
        </Modal>
      )}
      {editing && <BusinessDialog business={p} onClose={() => setEditing(false)} onSaved={() => { setEditing(false); load.reload() }} />}
    </main>
  )
}

function Overview({ p }: { p: BusinessDetail }) {
  if (p.ranges.length === 0) {
    return <div className="sh-empty">아직 연결된 검토가 없습니다. "이 사업에 RFP 등록"으로 검토를 만들어 주세요.</div>
  }
  return (
    <div className="pd-cards">{p.ranges.map((r, i) => {
      const go = rangeGo(r)
      return (
        <a key={r.run_id} className="pd-card" href={href(go.path)}>
          <span className="pd-ch"><span className="pd-lot">{p.ranges.length > 1 ? `범위 ${i + 1}` : '단일 발주'}</span><span className={RANGE_TONES[r.state]}>{RANGE_NAMES[r.state]}</span></span>
          <b className="pd-sc">{r.review_name ?? '설비 범위 없음'}</b>
          <span className="mono sh-mut">{r.review_no}</span>
          <span className="pd-own"><span className="hm-av" aria-hidden="true" style={{ width: 26, height: 26, fontSize: 11 }}>{(r.engineer_name ?? '?')[0]}</span>{r.engineer_name ?? '담당 없음'}</span>
          <span className="pd-note">{[r.open_requests ? `협조 미확인 ${r.open_requests}건` : '', r.due_date ? `검토 마감 ${dueText(r.due_date)}` : ''].filter(Boolean).join(' · ') || ' '}</span>
          <span className="pd-go">{go.label}<span className="ms" aria-hidden="true">chevron_right</span></span>
        </a>
      )
    })}</div>
  )
}

function People({ p, me }: { p: BusinessDetail; me: number | null }) {
  return (
    <>
      <h3 className="pd-h3">사내 담당자</h3>
      <div className="sh-box">
        <div className="pp-tr sh-th"><span>역할</span><span>이름</span><span>맡은 범위</span><span>직무</span><span /></div>
        {p.people.length === 0 && <div className="sh-empty">아직 담당자가 없습니다.</div>}
        {p.people.map((u) => (
          <div key={`${u.user_id}-${u.part}`} className="pp-tr pp-row">
            <span className="sh-mut" style={{ color: 'var(--c-text-3)', fontWeight: 600 }}>{PART_NAMES[u.part]}</span>
            <span className="pd-own"><span className="hm-av" aria-hidden="true" style={{ width: 28, height: 28, fontSize: 12 }}>{u.user_name[0]}</span>{u.user_name}{u.user_id === me && <span className="pp-me">나</span>}</span>
            <span className="sh-mut">{u.scope ?? '사업 전체'}</span>
            <span className="sh-mut">{ROLE_NAMES[u.role] ?? u.role}</span>
            <span style={{ textAlign: 'right' }}>{u.part === 'HELPER' && <a className="bo pp-btn" href={href('/todo')}>협조 요청</a>}</span>
          </div>
        ))}
      </div>
      <div className="sh-note"><span className="ms" aria-hidden="true">info</span><span>담당자는 연결된 검토의 담당 엔지니어, 결재자, 협조 요청 받은 사람과 사업의 영업 담당입니다. 고객 측 연락처는 저장하지 않습니다.</span></div>
    </>
  )
}
