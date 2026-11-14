import { useState } from 'react'
import { api, type Judgment } from '../api'
import { saveFile } from './download'
import { dday, stamp } from './format'
import { itemName, locShort, reqText } from './judgment'
import { RESULT_NAMES } from './labels'
import { useLoad } from './useLoad'
import { usePage } from './usePage'
import { Modal, useToast } from '../ui'

// 영업 인계 패키지 미리 보기 (add-package-preview, 목업 v4.96 "영업 인계 패키지" 창). 보기만 한다.
// 숫자는 제출본(v1) 기준 응답 값만 센다(CR-01), 팀 가정은 TBE 줄의 assumed (CR-06). 내려받기는 지금 zip 그대로.

type Tab = 'cover' | 'tbe' | 'out' | 'cost' | 'sales'
const SALES_ST: Record<string, string> = { TODO: '미발송', DOING: '회신 대기', DONE: '회신 완료' }
const TONE: Record<string, string> = { COMPLY: 'c-green', DEVIATION_CANDIDATE: 'c-red', QUERY_CANDIDATE: 'c-ora', NEEDS_REVIEW: 'c-ora', WARRANTY_TO_FILL: 'c-blue' }

/** 표지: 설비 묶음마다 준수·일탈·질의·확인 필요 수와 확인 필요 줄 3개 */
async function loadCover(runId: number) {
  const groups = await api.equipment(runId)
  const count = (group: string, result: string) => api.judgmentPage(runId, { group, result, limit: 1 }).then((p) => p.total)
  return Promise.all(groups.map(async (g) => {
    const [comply, query, review] = await Promise.all(['COMPLY', 'QUERY_CANDIDATE', 'NEEDS_REVIEW'].map((r) => count(g.equipment_group, r)))
    const top = await api.judgmentPage(runId, { group: g.equipment_group, result: 'NEEDS_REVIEW', limit: 3 })
    return { g, comply, query, review, top: top.items }
  }))
}

export function PackagePreview({ runId, onClose }: { runId: number; onClose: () => void }) {
  const toast = useToast()
  const [tab, setTab] = useState<Tab>('cover')
  const [busy, setBusy] = useState(false)
  const run = useLoad(() => api.run(runId), [runId])
  const screen = useLoad(() => api.approval(runId), [runId])
  const tbe = useLoad(() => api.tbe(runId, { include: 'all', lang: 'ko', base: 'v1' }), [runId])
  const cover = useLoad(() => loadCover(runId), [runId])
  const outs = useLoad(() => api.outputs(runId).then((o) => o.filter((x) => x.status !== 'REMOVED')), [runId])
  const cost = useLoad(() => api.costConditions(runId), [runId])
  const sales = useLoad(() => api.assignments('SALES').then((a) => a.filter((x) => x.run_id === runId)), [runId])
  const docs = useLoad(() => api.documents(runId), [runId])
  const r = run.data
  const a = screen.data?.approval
  const c = tbe.data?.counts
  const assumed = tbe.data ? tbe.data.rows.filter((x) => x.assumed).length : null
  const conds = cost.data?.conditions ?? []
  const tbePage = usePage(tbe.data?.rows ?? [])
  const outPage = usePage(outs.data ?? [])
  const costPage = usePage(conds)
  const salesPage = usePage(sales.data ?? [])
  const n = (v: number | null | undefined) => (v == null ? '—' : String(v))

  const download = () => {
    setBusy(true)
    api.downloadPackage(runId).then(({ name, blob }) => { saveFile(name, blob); toast.done(`${name} 를 내려받았습니다.`) },
      (e: Error) => toast.show(e.message, 'error')).finally(() => setBusy(false))
  }
  const dlButton = (
    <button type="button" className="bp" onClick={download} disabled={busy}>
      <span className="ms" aria-hidden="true" style={{ fontSize: 'var(--ic-s)' }}>download</span>{busy ? '만드는 중…' : '인계 패키지 내려받기'}</button>
  )
  const tabs: [Tab, string, number | null][] = [
    ['cover', '표지', null], ['tbe', 'TBE 준수표', tbe.data?.rows.length ?? null], ['out', '일탈·질의', outs.data?.length ?? null],
    ['cost', '견적 조건', cost.data ? conds.length : null], ['sales', '영업 할 일', sales.data?.length ?? null],
  ]
  const kpis: [string, number | null | undefined, string][] = [
    ['준수', c?.comply, ''], ['일탈', c?.deviation, 'c-red'], ['질의', c?.query, 'c-ora'],
    ['확인 필요', c?.review, 'c-ora'], ['팀 가정', assumed, ''], ['견적 조건', cost.data ? conds.length : null, ''],
  ]

  return (
    <Modal title="영업 인계 패키지" onClose={onClose} width={960}
      footer={<><span className="pkv-ft">zip 한 파일(일탈·질의 Word, TBE·데이터시트 엑셀)로 내려받습니다.</span>
        <button type="button" className="bo" onClick={onClose}>닫기</button>{dlButton}</>}>
      <div className="pkv">
        <div className="pkv-h">
          <p className="pkv-sub">{r ? <>{r.review_no} · {r.review_name ?? r.project_name ?? '이름 없음'}{r.customer_name && ` · ${r.customer_name}`}
            {r.due_date && <> · 제출 마감 {r.due_date.slice(5)} <b className={dday(r.due_date).cls}>{dday(r.due_date).text}</b></>}</> : '불러오는 중…'}</p>
          <span className="st c-green">결재 승인</span>
        </div>
        <div className="pkv-k" role="list" aria-label="인계 패키지 숫자">
          {kpis.map(([label, v, tone]) => <div key={label} role="listitem"><span>{label}</span><b className={tone}>{n(v)}</b></div>)}
        </div>
        <p className="pkv-ap">결재: {a?.approver ?? '—'} · 승인 {a?.decided_at ? stamp(a.decided_at) : '—'}
          {cover.data && cover.data.length > 0 && ` · 설비 ${cover.data.map((x) => x.g.label ?? x.g.equipment_group).join(', ')}`}</p>
        <p className="pkv-note">엔지니어가 확정하고 결재가 끝난 결과입니다. 금액은 비워 두었습니다. 영업·견적 담당이 채웁니다.</p>

        <div className="pkv-tabs" role="tablist" aria-label="인계 패키지 내용">
          {tabs.map(([k, label, cnt]) => (
            <button key={k} type="button" role="tab" aria-selected={tab === k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>
              {label}{cnt !== null && <span className="n">{cnt}</span>}</button>
          ))}
        </div>

        {tab === 'cover' && (
          <div className="pkv-cards">
            {cover.error && <p className="c-red">{cover.error}</p>}
            {!cover.data && !cover.error && <p className="dimv">불러오는 중…</p>}
            {cover.data?.length === 0 && <p className="dimv">설비 묶음이 없습니다.</p>}
            {cover.data?.map(({ g, comply, query, review, top }) => (
              <section key={g.equipment_group} className="pkv-card" data-testid="cover-card">
                <h3>{g.label ?? g.equipment_group}</h3>
                <p className="en">{r?.review_no}{g.chosen_product ? ` · 비교 제품 ${g.chosen_product}` : ' · 비교 제품 없음'}</p>
                <p className="pkv-cn">준수 <b>{comply}</b> 일탈 <b className="c-red">{g.deviations}</b> 질의 <b className="c-ora">{query}</b> 확인 필요 <b className="c-ora">{review}</b></p>
                {top.length > 0 && <ul>{top.map((j: Judgment) => (
                  <li key={j.judgment_id}><span className="st c-ora">확인 필요</span> {itemName(j)} — {reqText(j)}</li>
                ))}</ul>}
              </section>
            ))}
          </div>
        )}

        {tab === 'tbe' && (
          <>
            <table className="tbl pkv-t"><thead><tr><th>No</th><th>항목</th><th>요구</th><th>제안</th><th>판정</th><th>원문 위치</th></tr></thead>
              <tbody>{tbePage.shown.map((x) => (
                <tr key={x.judgment_id}><td>{x.no}</td><td>{x.item_ko ?? x.item}</td><td>{x.requirement}</td>
                  <td>{x.offered}{x.assumed && <span className="tag">팀 가정</span>}</td>
                  <td><span className={`st ${TONE[x.result] ?? ''}`}>{RESULT_NAMES[x.result] ?? x.verdict}</span></td>
                  <td className="en">{x.where}</td></tr>
              ))}</tbody></table>
            {tbePage.pager}
          </>
        )}

        {tab === 'out' && (
          <>
            {outs.data?.length === 0 && <p className="dimv">일탈·질의 후보가 없습니다.</p>}
            <table className="tbl pkv-t"><tbody>{outPage.shown.map((o) => (
              <tr key={o.item_id}><td style={{ width: 70 }}><span className={`st ${o.list_kind === 'DEVIATION' ? 'c-red' : 'c-ora'}`}>{o.list_kind === 'DEVIATION' ? '일탈' : '질의'}</span></td>
                <td>{o.text_draft}<div className="en">{locShort(o, docs.data ?? [])}</div></td></tr>
            ))}</tbody></table>
            {outPage.pager}
          </>
        )}

        {tab === 'cost' && (
          <>
            {cost.data && conds.length === 0 && <p className="dimv">찾은 비용 조건이 없습니다.</p>}
            <table className="tbl pkv-t"><tbody>{costPage.shown.map((x) => (
              <tr key={x.requirement_id}><td style={{ width: 120 }}><b>{x.kind}</b></td>
                <td>{x.values.length > 0 && <b>{x.values.join(' · ')} </b>}<span className="en">{x.text}</span></td>
                <td style={{ width: 90 }}>{SALES_ST[x.request_status ?? ''] ?? '협조 요청 없음'}</td></tr>
            ))}</tbody></table>
            {costPage.pager}
          </>
        )}

        {tab === 'sales' && (
          <>
            {sales.data?.length === 0 && <p className="dimv">영업 담당 협조 요청이 없습니다.</p>}
            <table className="tbl pkv-t"><tbody>{salesPage.shown.map((x) => (
              <tr key={x.assignment_id}><td>{x.text}</td><td style={{ width: 90 }}>{SALES_ST[x.status] ?? x.status}</td></tr>
            ))}</tbody></table>
            {salesPage.pager}
          </>
        )}
      </div>
    </Modal>
  )
}
