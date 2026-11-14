import { useEffect, useState } from 'react'
import { api, type ItemKey, type ProductDetail, type RunListItem } from '../api'
import { saveFile } from '../components/download'
import { Pager } from '../components/Pager'
import { FAMILY_NAMES, STAGE_NAMES, STAGE_TONES } from '../components/labels'
import { useLoad } from '../components/useLoad'
import {
  COLS, NO_REQ, SHORT, alternatives, blocked, cell, dday, fit, reqOn, runUses, strength, resultCounts, valueKind, type Req,
} from '../components/productSpec'
import { href, pathQuery, useHashPath } from '../shell/router'
import { usePageCss } from '../shell/pageCss'
import { useSession } from '../shell/useSession'

// SCR-16 제품표 (목업 v4.96 Products). docs/screens/SCR-16-제품표.md
// 읽기만 한다. 빈 칸은 "비어 있음", 그 제품군에 없는 칸은 "—", 팀 가정 값은 "팀 가정" (CR-04, CR-06).
// 줄을 누르면 오른쪽 빠른 보기, 제품 코드를 누르면 제품 상세 화면(SCR-16-1, ProductView). 요구 조건으로 찾기는 화면에서 거른다 (add-product-view).

const LOCK = '제품표는 이 화면에서 수정할 수 없습니다. 제품 담당에게 요청하세요.'
const ALL = 500                    // 요구 조건으로 찾기를 켜면 한 번에 받는 제품 수 (design.md 5)
const QV_SPECS = ['rated_voltage_kv', 'rated_current_a', 'short_circuit_ka', 'peak_current_ka', 'rated_frequency']
const QV_TR = ['rated_voltage_kv', 'rated_capacity', 'noload_loss_kw', 'load_loss_kw', 'rated_frequency']

export function Products() {
  usePageCss('Products')
  usePageCss('ProductsV496')
  const path = useHashPath()
  const [view, setView] = useState<'list' | 'cmp'>('list')
  const [fam, setFam] = useState('all')
  const [q, setQ] = useState('')
  const [cards, setCards] = useState(true)
  const [page, setPage] = useState(1)
  const [size, setSize] = useState(10)
  const [sel, setSel] = useState<string[]>([])
  // 목업처럼 처음에는 목록 첫 제품의 빠른 보기를 편다. 상세 화면에서 [제품표]로 오면 그 제품(?code=). 닫으면(null) 다시 열지 않는다
  const [picked, setCur] = useState<string | null | undefined>(() => pathQuery(path).get('code') ?? undefined)
  const [diffOnly, setDiffOnly] = useState(false)
  const [exp, setExp] = useState<{ busy: boolean; note: { ok: boolean; text: string } | null }>({ busy: false, note: null })
  const [rqShow, setRqShow] = useState(false)
  const [rq, setRq] = useState<Req>(NO_REQ)
  const [rqFrom, setRqFrom] = useState('')
  const [finding, setFinding] = useState(false)
  const fams = useLoad(() => api.productFamilies(), [])
  const items = useLoad(() => api.ruleItems(), [])
  const filtering = rqShow && reqOn(rq)
  const params = { family: fam === 'all' ? undefined : fam, q: q.trim() || undefined, cards: cards ? undefined as undefined : 'false' as const }
  const list = useLoad(() => api.products({ ...params, offset: filtering ? 0 : (page - 1) * size, limit: filtering ? ALL : size }),
    [fam, q, page, size, cards, filtering])
  const cmp = useLoad(() => Promise.all(sel.map((c) => api.product(c))), [sel.join(',')])

  const all = fams.data ?? []
  const total = all.reduce((n, f) => n + f.products, 0)
  const sum = (k: 'empty_cells' | 'assumed' | 'design_cards' | 'with_empty') => all.reduce((n, f) => n + f[k], 0)
  const got = list.data?.items ?? []
  const fits = filtering ? got.map((p) => ({ p, f: fit(p, rq) })) : []
  const matched = fits.filter((x) => x.f.ok).map((x) => x.p)
  const count = filtering ? matched.length : list.data?.total ?? 0
  const pages = Math.max(1, Math.ceil(count / size))
  const curPage = Math.min(page, pages)
  const rows = filtering ? matched.slice((curPage - 1) * size, curPage * size) : got
  const cur = picked === undefined ? rows[0]?.product_code ?? null : picked
  const detail = useLoad(() => (cur ? api.product(cur) : Promise.resolve(null)), [cur])
  // 내보내기 (add-product-export): 지금 목록과 같은 거르기(제품군·검색어·설계 사례 카드)로 엑셀 한 장
  const exportXlsx = () => {
    if (exp.busy) return
    setExp({ busy: true, note: null })
    api.exportProducts(params)
      .then(({ name, blob }) => { saveFile(name, blob); setExp({ busy: false, note: { ok: true, text: `${name} 를 내려받았습니다.` } }) },
        (e: Error) => setExp({ busy: false, note: { ok: false, text: e.message } }))
  }
  const toggle = (code: string) => setSel(sel.includes(code) ? sel.filter((c) => c !== code) : [...sel, code])
  const setReq = (k: keyof Req, v: string) => { setRq({ ...rq, [k]: v.replace(/[^\d.]/g, '') }); setRqFrom(''); setPage(1) }
  const nOf = (k: 'ok' | 'short' | 'none') => fits.filter((x) => x.f.kind === k).length

  return (
    <main className="main">
      <nav className="pgtabs" aria-label="제품표 메뉴">
        <a className={view === 'list' ? 'on' : ''} href="#/products" onClick={(e) => { e.preventDefault(); setView('list') }}>제품 목록</a>
        <a className={view === 'cmp' ? 'on' : ''} href="#/products" onClick={(e) => { e.preventDefault(); setView('cmp') }}>비교 ({sel.length})</a>
      </nav>
      <div className="idl"><span>제품 {total} · 제품군 {all.length}</span><span>현재 제품표 기준 (이전 검토에 쓴 제품표와 다를 수 있음)</span></div>
      <div className="ttl">
        <h1>제품표</h1>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <span title={LOCK}><button type="button" className="bo" disabled><span className="ms" aria-hidden="true" style={{ fontSize: 'var(--ic-s)' }}>upload</span>엑셀 가져오기</button></span>
          <button type="button" className="bo" onClick={exportXlsx} disabled={exp.busy} title="지금 목록의 거르기(제품군·검색어·설계 사례 카드)대로 엑셀로 내려받습니다"><span className="ms" aria-hidden="true" style={{ fontSize: 'var(--ic-s)' }}>download</span>{exp.busy ? '만드는 중…' : '내보내기'}</button>
        </div>
      </div>
      {exp.note && <p role={exp.note.ok ? 'status' : 'alert'} className={exp.note.ok ? 'pxnote' : 'pxnote c-red'}>{exp.note.text}</p>}
      <div className="kpis">
        <div className="kpi"><div className="l">비어 있는 칸</div><b className="c-ora">{fams.data ? sum('empty_cells') : '—'}</b><div className="s">판정에 쓰는 칸 · 제품 {sum('with_empty')}개</div></div>
        <div className="kpi"><div className="l">팀 가정 값</div><b className="c-blue">{fams.data ? sum('assumed') : '—'}</b><div className="s">변압기 손실값 등</div></div>
        <div className="kpi"><div className="l">설계 사례 카드</div><b>{fams.data ? sum('design_cards') : '—'}</b><div className="s">기본 비교 제품 아님</div></div>
      </div>

      {view === 'list' ? (
        <section className="sec" style={{ marginTop: 24 }}>
          <div className="fbar">
            {[{ family: 'all', products: total }, ...all].map((f) => (
              <button key={f.family} type="button" className={`chip${fam === f.family ? ' on' : ''}`} aria-pressed={fam === f.family}
                onClick={() => { setFam(f.family); setPage(1) }}>{f.family === 'all' ? '전체' : FAMILY_NAMES[f.family] ?? f.family} <span className="n">{f.products}</span></button>
            ))}
            <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 'var(--fs-sm)', color: 'var(--c-text-3)', marginLeft: 4 }}>
              <input type="checkbox" checked={cards} onChange={(e) => { setCards(e.target.checked); setPage(1) }} style={{ accentColor: 'var(--c-link)' }} />설계 사례 카드 포함</label>
            <span style={{ flex: '1 1 0' }} />
            <label className="sr" htmlFor="pq">제품 검색</label>
            <input className="fi" id="pq" value={q} onChange={(e) => { setQ(e.target.value); setPage(1) }} placeholder="제품 코드, 이름" style={{ width: 180 }} />
            <button type="button" className={rqShow ? 'bp' : 'bo'} aria-pressed={rqShow} onClick={() => { setRqShow(!rqShow); setPage(1) }}>
              <span className="ms" aria-hidden="true" style={{ fontSize: 'var(--ic-s)' }}>manage_search</span>요구 조건으로 찾기</button>
            <button type="button" className="bp" disabled={sel.length < 2} onClick={() => setView('cmp')}><span className="ms" aria-hidden="true" style={{ fontSize: 'var(--ic-s)' }}>compare_arrows</span>선택한 {sel.length}개 비교</button>
          </div>
          {rqShow && (
            <div className="rqbar" role="search" aria-label="요구 조건">
              <span className="rqt">요구 조건<button type="button" className="rqf" onClick={() => setFinding(true)} title="RFP 검토에서 요구값 가져오기">RFP 검토 찾기<span className="ms" aria-hidden="true">search</span></button>
                <small>{rqFrom || '값 이상인 제품만 보입니다 (단위는 바꾸지 않음)'}</small></span>
              <label>정격 전압<span><input className="fi" value={rq.kv} onChange={(e) => setReq('kv', e.target.value)} inputMode="decimal" aria-label="정격 전압 (kV)" />kV</span></label>
              <label>정격 전류 이상<span><input className="fi" value={rq.a} onChange={(e) => setReq('a', e.target.value)} inputMode="decimal" aria-label="정격 전류 이상 (A)" />A</span></label>
              <label>단시간 견딤 이상<span><input className="fi" value={rq.ka} onChange={(e) => setReq('ka', e.target.value)} inputMode="decimal" aria-label="단시간 견딤 이상 (kA)" />kA</span></label>
              <span className="rqsum">{filtering ? `모두 맞음 ${nOf('ok')} · 모자람 ${nOf('short')} · 값 없음 ${nOf('none')}` : '값을 넣으면 맞는 제품만 남습니다'}</span>
            </div>
          )}
          <div className={`work${cur ? ' open' : ''}`}>
            <div style={{ minWidth: 0 }}>
              <div className="tw">
                <table className="tbl">
                  <thead><tr>
                    <th style={{ width: 28 }}><span className="sr">비교에 넣기</span></th>
                    <th>제품</th>{filtering && <th style={{ minWidth: 190 }}>요구 충족</th>}<th>제품군</th>
                    {COLS.map((c) => <th key={c.key} style={c.key === 'rated_frequency' ? undefined : { textAlign: 'right' }}>{SHORT[c.key]}</th>)}
                  </tr></thead>
                  <tbody>
                    {list.data === null && !list.error && <tr><td colSpan={COLS.length + 3} className="dimv">불러오는 중…</td></tr>}
                    {rows.map((p) => {
                      const f = filtering ? fit(p, rq) : null
                      return (
                        <tr key={p.product_code} className={cur === p.product_code ? 'cur' : undefined} onClick={() => { setCur(p.product_code) }} style={{ cursor: 'pointer' }}>
                          <td onClick={(e) => e.stopPropagation()}><input type="checkbox" aria-label={`${p.product_code} 비교에 넣기`} checked={sel.includes(p.product_code)}
                            disabled={!sel.includes(p.product_code) && sel.length >= 3} onChange={() => toggle(p.product_code)} style={{ accentColor: 'var(--c-link)', marginTop: 2 }} /></td>
                          <td style={{ whiteSpace: 'nowrap' }}><a className="pcode" href={href(`/products/${encodeURIComponent(p.product_code)}`)} onClick={(e) => e.stopPropagation()}
                            title="제품 상세 화면 열기">{p.product_code}</a>{p.is_design_card && <span className="tag">설계 사례</span>}
                            <div className="en">{p.source_doc}</div></td>
                          {f && <td><span className={`fit ${f.cls}`}>{f.text}</span></td>}
                          <td>{FAMILY_NAMES[p.family] ?? p.family}</td>
                          {COLS.map((c) => {
                            const x = cell(p, c.key)
                            return <td key={c.key} style={c.key === 'rated_frequency' ? undefined : { textAlign: 'right', whiteSpace: 'nowrap' }}>
                              <span className={x.cls}>{x.text}</span>{x.sub && <div className="en c-blue">{x.sub}</div>}</td>
                          })}
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
                {rows.length > 0 && <Pager total={count} page={curPage} size={size} shown={rows.length} onPage={setPage} onSize={(n) => { setSize(n); setPage(1) }} />}
              </div>
              {list.error && <p role="alert">{list.error}</p>}
              {list.data !== null && rows.length === 0 && <p style={{ margin: 0, padding: '16px 10px', color: 'var(--c-muted)' }}>조건에 맞는 제품이 없습니다.</p>}
              <div className="tfoot"><span>{rows.length}개 표시 · 주요 {COLS.length}칸 (전체 칸은 제품 코드를 눌러 제품 상세 화면에서)</span><span>— 해당 없음 · <span className="c-ora">비어 있음</span> · 팀 가정</span></div>
            </div>
            {cur && <QuickView code={cur} data={detail.data} error={detail.error} items={items.data ?? []} inCmp={sel.includes(cur)}
              cmpFull={sel.length >= 3} onCmp={() => toggle(cur)} onPick={setCur} onClose={() => setCur(null)} />}
          </div>
        </section>
      ) : (
        <Compare products={cmp.data ?? []} items={items.data ?? []} diffOnly={diffOnly} onDiff={setDiffOnly} onBack={() => setView('list')} />
      )}
      {finding && <ReviewFinder onClose={() => setFinding(false)}
        onApply={(r, from) => { setRq(r); setRqFrom(from); setRqShow(true); setPage(1); setFinding(false) }} />}
    </main>
  )
}

/** 오른쪽 빠른 보기 (목업 v4.96 .qv): 핵심 정격, 값이 없어 막힌 판정, 지금 쓰이는 검토, 대신 쓸 수 있는 제품 */
function QuickView({ code, data, error, items, inCmp, cmpFull, onCmp, onPick, onClose }: {
  code: string; data: ProductDetail | null; error: string | null; items: ItemKey[]; inCmp: boolean; cmpFull: boolean
  onCmp: () => void; onPick: (code: string) => void; onClose: () => void
}) {
  const p = data?.product_code === code ? data : null
  const same = useLoad(() => (p ? api.products({ family: p.family, cards: 'false', limit: ALL }) : Promise.resolve(null)), [p?.family])
  const specs = p ? (p.family === 'TR' ? QV_TR : QV_SPECS) : []
  const blocks = p ? blocked(p, items) : []
  const uses = p ? runUses(p) : []
  const alts = p && same.data ? alternatives(p, same.data.items, items) : []
  return (
    <aside className="panel" aria-label="제품 빠른 보기">
      <div className="ph">
        <div style={{ flex: '1 1 auto', minWidth: 0 }}><div className="en" style={{ margin: '0 0 2px' }}>{p ? `${FAMILY_NAMES[p.family] ?? p.family} · ${valueKind(p)}` : '불러오는 중…'}</div><h3>{code}</h3></div>
        <button type="button" className="ib" aria-label="닫기" onClick={onClose}><span className="ms" aria-hidden="true">close</span></button>
      </div>
      {error && <p role="alert" style={{ padding: '0 16px' }}>{error}</p>}
      {p && (
        <div className="qv">
          <div className="qv-act"><a className="bp" href={href(`/products/${encodeURIComponent(code)}`)}><span className="ms" aria-hidden="true" style={{ fontSize: 'var(--ic-s)' }}>open_in_new</span>상세 화면</a>
            <button type="button" className="bo" onClick={onCmp} disabled={!inCmp && cmpFull}>{inCmp ? '비교에 넣음' : '비교에 넣기'}</button></div>
          <h4>핵심 정격</h4>
          <table className="qv-t"><tbody>{specs.map((k) => {
            const c = [...COLS].find((x) => x.key === k)!
            const x = cell(p, k)
            return <tr key={k}><th>{c.label}{c.unit && ` (${c.unit})`}</th><td><b className={x.cls}>{x.text}</b></td>
              <td><span className={x.state === 'assume' ? 'c-blue' : x.state === 'empty' ? 'c-ora' : 'dimv'}>
                {x.state === 'ok' ? p.source_doc : x.state === 'assume' ? '팀 가정' : x.state === 'empty' ? '판정 때 확인 필요' : '해당 없음'}</span></td></tr>
          })}</tbody></table>
          {blocks.length > 0 && (
            <div className="qv-blk"><h4><span className="ms" aria-hidden="true">warning</span>값이 없어 막힌 판정 {blocks.length}</h4>
              {blocks.slice(0, 3).map((b) => <div key={b.judgment_id} className="qv-b"><span><b>{b.item_name}</b> — {b.review_no} 확인 필요</span>
                <span title="값 요청 기능은 준비 중입니다"><button type="button" className="bo" disabled>값 요청</button></span></div>)}
            </div>
          )}
          <h4>지금 쓰이는 검토 <span className="n">{p.used_runs}</span></h4>
          {!uses.length && <p className="qv-e">진행 중인 검토에 쓰이지 않습니다.</p>}
          {uses.slice(0, 4).map((u) => {
            const d = dday(u.due_date)
            return <a key={u.run_id} className="qv-u" href={href(`/reviews/${u.run_id}`)}><span className="mono">{u.review_no}</span>
              <span className="nm">{u.review_name ?? '이름 없음'}<small>{resultCounts(u)}</small></span>{d && <span className={`dd${d.late ? ' red' : ''}`}>{d.text}</span>}</a>
          })}
          <h4>대신 쓸 수 있는 제품</h4>
          {same.data && !alts.length && <p className="qv-e">같은 제품군에 더 높은 정격 제품이 없습니다.</p>}
          {alts.map((a) => <button key={a.code} type="button" className="qv-a" onClick={() => onPick(a.code)}><b>{a.code}</b><span>{a.why}</span>
            <span className="ms" aria-hidden="true">chevron_right</span></button>)}
          <p className="qv-e">참고용입니다. 판정의 비교 제품은 바꾸지 않습니다.</p>
        </div>
      )}
    </aside>
  )
}

type Pick = { kv: string; a: string; ka: string }
const REQ_KEYS: [keyof Pick, string][] = [['kv', 'rated_voltage_um'], ['a', 'rated_current'], ['ka', 'short_time_current']]
const DONE = new Set(['APPROVED', 'REJECTED', 'FAILED'])
const LOAD_ROWS = 8

/** 그 검토 판정에서 요구값 첫 값 (정격 전압·정격 전류·단시간). 없으면 빈칸 (CR-04, design.md 6) */
async function reqOf(runId: number): Promise<Pick> {
  const js = await api.judgments(runId, { limit: 500 })
  const out: Pick = { kv: '', a: '', ka: '' }
  for (const [k, item] of REQ_KEYS) {
    const j = js.find((x) => x.item_key === item && x.req_num !== null)
    if (j) out[k] = String(j.req_num)
  }
  return out
}

/** RFP 검토 찾기 창 (목업 v4.96 .rvw): 검토를 골라 그 요구값을 요구 조건에 넣는다 */
function ReviewFinder({ onClose, onApply }: { onClose: () => void; onApply: (r: Req, from: string) => void }) {
  const { user } = useSession()
  const runs = useLoad(() => api.runs(), [])
  const [f, setF] = useState({ pj: '', cust: '', st: 'all', own: 'all', q: '' })
  const [applied, setApplied] = useState(f)
  const [pick, setPick] = useState<number | null>(null)
  const [vals, setVals] = useState<Record<number, Pick>>({})
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  const all = (runs.data ?? []).filter((r) => r.stage !== 'PROCESSING' && r.stage !== 'FAILED')
  const pjs = [...new Set(all.map((r) => r.project_name).filter((x): x is string => !!x))].sort()
  const custs = [...new Set(all.map((r) => r.customer_name).filter((x): x is string => !!x))].sort()
  const q = applied.q.trim().toLowerCase()
  const rows = all.filter((r) => (!applied.pj || r.project_name === applied.pj) && (!applied.cust || r.customer_name === applied.cust)
    && (applied.st === 'all' || (applied.st === 'done' ? DONE.has(r.stage) : !DONE.has(r.stage)))
    && (applied.own === 'all' || r.engineer_id === user?.user_id)
    && (!q || [r.review_no, r.review_name, r.project_name].filter(Boolean).join(' ').toLowerCase().includes(q)))
  const want = rows.slice(0, LOAD_ROWS).map((r) => r.run_id).filter((id) => !(id in vals))
  useEffect(() => {
    if (!want.length) return
    let alive = true
    Promise.all(want.map((id) => reqOf(id).then((v) => [id, v] as const, () => [id, { kv: '', a: '', ka: '' }] as const)))
      .then((got) => { if (alive) setVals((m) => ({ ...m, ...Object.fromEntries(got) })) })
    return () => { alive = false }
  }, [want.join(',')])  // eslint-disable-line react-hooks/exhaustive-deps
  const picked = rows.find((r) => r.run_id === pick) ?? null
  const reqLabel = (r: RunListItem) => {
    const v = vals[r.run_id]
    if (!v) return rows.indexOf(r) < LOAD_ROWS ? '불러오는 중…' : '고르면 불러옵니다'
    return [v.kv && `${v.kv} kV`, v.a && `${v.a} A`, v.ka && `${v.ka} kA`].filter(Boolean).join(' · ') || '요구값 없음'
  }
  const apply = async () => {
    if (!picked) return
    const v = vals[picked.run_id] ?? await reqOf(picked.run_id)
    onApply({ kv: v.kv, a: v.a, ka: v.ka }, `${picked.review_no} 요구사항에서 가져옴`)
  }
  const radios = (name: string, key: 'st' | 'own', opts: [string, string][]) => (
    <div className="rvr" role="radiogroup" aria-label={name}><span>{name}</span>
      {opts.map(([v, l]) => <label key={v} className="rd"><input type="radio" name={`rv${key}`} checked={f[key] === v} onChange={() => setF({ ...f, [key]: v })} />{l}</label>)}</div>
  )
  return (
    <div className="rvo" onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="rvw" role="dialog" aria-modal="true" aria-labelledby="rvTitle">
        <div className="rvh"><h2 id="rvTitle">RFP 검토 찾기</h2><span className="rvs">검토를 고르면 그 검토의 요구값을 요구 조건에 넣습니다</span>
          <button type="button" className="ib" onClick={onClose} aria-label="닫기" title="닫기 (Esc)" autoFocus><span className="ms" aria-hidden="true">close</span></button></div>
        <div className="rvf" role="search" aria-label="RFP 검토 검색 조건">
          <label>사업명<select className="fi" value={f.pj} onChange={(e) => setF({ ...f, pj: e.target.value })}><option value="">모든 사업</option>{pjs.map((x) => <option key={x}>{x}</option>)}</select></label>
          <label>고객사<select className="fi" value={f.cust} onChange={(e) => setF({ ...f, cust: e.target.value })}><option value="">모든 고객사</option>{custs.map((x) => <option key={x}>{x}</option>)}</select></label>
          {radios('진행 상태', 'st', [['all', '전체'], ['open', '진행 중'], ['done', '끝남']])}
          {radios('담당', 'own', [['all', '전체'], ['mine', '내 검토']])}
          <div className="rvq"><label className="sr" htmlFor="rvq">검토명 (RFP)</label><input className="fi" id="rvq" value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })}
            onKeyDown={(e) => { if (e.key === 'Enter') setApplied(f) }} placeholder="검토명 (RFP), 검토 번호 — 예: GIS, RV-2026-025" />
            <button type="button" className="bo" onClick={() => { const z = { pj: '', cust: '', st: 'all', own: 'all', q: '' }; setF(z); setApplied(z) }}>초기화</button>
            <button type="button" className="bp" onClick={() => setApplied(f)}><span className="ms" aria-hidden="true" style={{ fontSize: 'var(--ic-s)' }}>search</span>검색</button></div>
        </div>
        <div className="rvl">
          <div className="rvn">검토 {rows.length}건</div>
          <table className="tbl rvt">
            <thead><tr><th style={{ width: 32 }} /><th>검토 번호</th><th>검토명</th><th>사업명 · 고객사</th><th>상태</th><th>마감</th><th>요구값 (전압 · 정격 전류 · 단시간)</th></tr></thead>
            <tbody>{rows.map((r) => (
              <tr key={r.run_id} className={pick === r.run_id ? 'on' : undefined} onClick={() => setPick(r.run_id)}>
                <td><input type="radio" name="rvpick" checked={pick === r.run_id} onChange={() => setPick(r.run_id)} aria-label={`${r.review_no} 고르기`} /></td>
                <td className="mono">{r.review_no}</td><td style={{ fontWeight: 600 }}>{r.review_name ?? '—'}</td>
                <td>{r.project_name ?? '—'}<div className="en">{r.customer_name ?? ''}</div></td>
                <td><span className={`st ${STAGE_TONES[r.stage] ?? 'c-grey'}`}>{STAGE_NAMES[r.stage] ?? r.stage}</span></td>
                <td>{r.due_date ?? '—'}</td><td>{reqLabel(r)}</td>
              </tr>))}</tbody>
          </table>
          {runs.data !== null && !rows.length && <p className="rve">조건에 맞는 검토가 없습니다.</p>}
        </div>
        <div className="rvft"><span>{picked ? `${picked.review_no} ${reqLabel(picked)}` : '검토를 고르세요'}</span><span style={{ flex: '1 1 0' }} />
          <button type="button" className="bo" onClick={onClose}>취소</button>
          <button type="button" className="bp" onClick={() => { void apply() }} disabled={!picked}>요구값 넣기</button></div>
      </div>
    </div>
  )
}

/** 두세 제품을 칸마다 나란히. 값이 다른 줄은 노랗게, 강점 방향으로 가장 유리한 값에 ▲ */
function Compare({ products, items, diffOnly, onDiff, onBack }: {
  products: ProductDetail[]; items: ItemKey[]; diffOnly: boolean; onDiff: (v: boolean) => void; onBack: () => void
}) {
  const rows = COLS.map((c) => {
    const cs = products.map((p) => cell(p, c.key))
    const differs = new Set(cs.map((x) => x.text)).size > 1
    const dir = strength(c, items)
    const nums = products.map((p) => { const v = (p as Record<string, unknown>)[c.key]; return typeof v === 'string' && /^-?\d+(\.\d+)?$/.test(v) ? Number(v) : null })
    let best = -1
    const known = nums.filter((n): n is number => n !== null)
    if (differs && dir !== '강점 아님' && known.length >= 2) {
      const pick = dir === '클수록 강점' ? Math.max(...known) : Math.min(...known)
      if (known.filter((n) => n === pick).length === 1) best = nums.indexOf(pick)
    }
    return { c, cs, differs, dir, best }
  }).filter((r) => !diffOnly || r.differs)
  return (
    <section className="sec" style={{ marginTop: 24 }}>
      <div className="sech">
        <h2>제품 비교<span className="note">{products.map((p) => p.product_code).join(' · ')}</span></h2>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 'var(--fs-sm)', color: 'var(--c-text-3)' }}>
            <input type="checkbox" checked={diffOnly} onChange={(e) => onDiff(e.target.checked)} style={{ accentColor: 'var(--c-link)' }} />다른 값만 보기</label>
          <button type="button" className="bo" onClick={onBack}>목록으로</button>
        </div>
      </div>
      {products.length < 2 && <p style={{ color: 'var(--c-muted)' }}>목록에서 비교할 제품을 2개 이상 고르세요.</p>}
      {products.length >= 2 && (
        <>
          <div className="tw">
            <table className="tbl" style={{ marginTop: 12 }}>
              <thead><tr><th style={{ width: 180 }}>항목</th><th style={{ width: 110 }}>강점 방향</th>{products.map((p) => <th key={p.product_code} style={{ textAlign: 'right' }}>{p.product_code}</th>)}</tr></thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.c.key} className={r.differs ? 'diff' : undefined} style={{ cursor: 'default' }}>
                    <td style={{ fontWeight: 600 }}>{r.c.label}{r.c.unit && ` (${r.c.unit})`}</td>
                    <td className="en" style={{ margin: 0, paddingTop: 10 }}>{r.dir}</td>
                    {r.cs.map((x, i) => <td key={i} style={{ textAlign: 'right' }}><span className={x.cls}>{x.text}{x.sub && ` · ${x.sub}`}</span>
                      {i === r.best && <span className="best" title="이 항목에서 가장 유리한 값">▲</span>}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="tfoot"><span>노란 줄: 제품끼리 값이 다른 항목 · ▲ 강점 방향으로 가장 유리한 값</span><span>강점 방향은 항목 이름 사전 기준 (손실은 작을수록 강점)</span></div>
        </>
      )}
    </section>
  )
}
