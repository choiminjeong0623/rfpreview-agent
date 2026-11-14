import { useState } from 'react'
import { api } from '../api'
import { DOC_KINDS, isSourceCatalog, productDocs } from '../components/productDocs'
import { productPhoto } from '../components/productPhotos'
import { FAMILY_NAMES, RESULT_NAMES, RESULT_TONES } from '../components/labels'
import { useLoad } from '../components/useLoad'
import { COLS, SPEC_COLS, assumedCount, blocked, cell, dday, runUses, resultCounts, strength, valueKind } from '../components/productSpec'
import { useCrumbTail } from '../shell/crumb'
import { href } from '../shell/router'
import { usePageCss } from '../shell/pageCss'
import { ExampleBand } from './detail/ExampleTab'

// SCR-16-1 제품 상세 (목업 v4.96 ProductView, change add-product-view). docs/screens/SCR-16-1-제품상세.md
// 읽기만 한다. 빈 칸은 "비어 있음", 팀 가정 값은 "팀 가정" (CR-04, CR-06). 사진·문서는 제품 계열 공통 자료.
// 현장 조건 보정·옵션 칸·규격·인증 표·문서 보기는 만들지 않는다 (SCR-16_공유.md).

type Tab = 'spec' | 'phys' | 'hist' | 'field'
const TABS: [Tab, string][] = [['spec', '정격'], ['phys', '치수·운송'], ['hist', '쓰인 곳'], ['field', '현장 이력']]

export function ProductView({ code }: { code: string }) {
  usePageCss('Products')
  usePageCss('ProductsV496')
  const [tab, setTab] = useState<Tab>('spec')
  const [bids, setBids] = useState(false)
  const data = useLoad(() => api.product(code), [code])
  const items = useLoad(() => api.ruleItems(), [])
  useCrumbTail(code)
  const p = data.data
  const back = <a className="bo" href={href(`/products?code=${encodeURIComponent(code)}`)}><span className="ms" aria-hidden="true" style={{ fontSize: 'var(--ic-s)' }}>list</span>제품표</a>
  if (data.error) {
    const missing = /제품표에 없습니다/.test(data.error)
    return (
      <main className="main pvp">
        <div className="ttl"><div className="ttl1"><h1>{code}</h1></div>{back}</div>
        <p role="alert">{missing ? `제품표에 없는 제품입니다 (${code})` : data.error}</p>
        {!missing && <button type="button" className="bo" onClick={data.reload}>다시 불러오기</button>}
      </main>
    )
  }
  if (!p) return <main className="main pvp"><div className="ttl"><div className="ttl1"><h1>{code}</h1></div></div><p className="dimv">불러오는 중…</p></main>
  const its = items.data ?? []
  const blocks = blocked(p, its)
  const uses = runUses(p)
  const fam = FAMILY_NAMES[p.family] ?? p.family
  const kv = cell(p, 'rated_voltage_kv')
  const hist = Object.entries(p.used_in.reduce<Record<string, number>>((m, u) => ({ ...m, [u.result]: (m[u.result] ?? 0) + 1 }), {}))
    .sort((a, b) => b[1] - a[1])
  return (
    <main className="main pvp">
      <div className="ttl">
        <div style={{ minWidth: 0 }}>
          <div className="ttl1"><h1>{p.product_code}</h1><span className="tag">{fam}</span>{p.is_design_card && <span className="tag c-ora">설계 사례</span>}</div>
          <div className="ttl2">{valueKind(p)} · 출처 {p.source_doc ?? '없음'}</div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {back}
          <span title="제품표는 읽기 전용입니다"><button type="button" className="bp" disabled>
            <span className="ms" aria-hidden="true" style={{ fontSize: 'var(--ic-s)' }}>lock</span>수정 요청</button></span>
        </div>
      </div>
      <div className="hc3">
        <section aria-label="제품"><h3>제품</h3><dl>
          <div><dt>제품군</dt><dd>{fam}</dd></div><div><dt>정격 전압</dt><dd>{kv.state === 'na' ? '—' : `${kv.text} kV`}</dd></div>
          <div><dt>값 종류</dt><dd>{valueKind(p)}</dd></div><div><dt>갱신</dt><dd>현재 제품표</dd></div></dl></section>
        <section aria-label="근거 상태"><h3>근거 상태</h3><div className="kv3">
          <div><span>팀 가정</span><b className="c-blue">{assumedCount(p)}</b></div><div><span>빈칸</span><b className="c-ora">{p.empty_count}</b></div></div></section>
        <section aria-label="쓰임"><h3>쓰임</h3><div className="kv3">
          <div><span>진행 중 검토</span><b>{p.used_runs}</b></div><div><span>값이 없어 막힌 판정</span><b className="c-ora">{blocks.length}</b></div>
          <div><span>제안 포인트</span><b className="c-green">{p.proposals.length}</b></div></div>
          {blocks.slice(0, 3).map((b) => <div key={b.judgment_id} className="qv-b" style={{ marginTop: 8 }}>
            <span><b>{b.item_name}</b> — <a href={href(`/reviews/${b.run_id}/judgments/${b.judgment_id}`)}>{b.review_no}</a> 확인 필요</span>
            <span title="값 요청 기능은 준비 중입니다"><button type="button" className="bo" disabled>값 요청</button></span></div>)}
        </section>
      </div>
      <div className="pmw pvw">
        <div className="pmb">
          <aside className="pml">
            <Photo sourceDoc={p.source_doc} />
            <div className="lbl">관련 문서</div>
            <Docs sourceDoc={p.source_doc} />
          </aside>
          <section className="pmr">
            <div className="ptab2" role="tablist">
              {TABS.map(([k, l]) => <button key={k} type="button" role="tab" className={tab === k ? 'on' : ''} aria-selected={tab === k} onClick={() => setTab(k)}>{l}</button>)}
            </div>
            <div className="pinfo">
              <div className="upd"><span className="ms" aria-hidden="true" style={{ fontSize: 15 }}>update</span>현재 제품표 기준</div>
              {tab === 'spec' && <>
                <table className="tbl">
                  <thead><tr><th>항목</th><th style={{ textAlign: 'right' }}>값</th><th>비교 방향</th><th>근거</th></tr></thead>
                  <tbody>{SPEC_COLS.map((c) => {
                    const x = cell(p, c.key)
                    if (x.state === 'na') return null
                    return <tr key={c.key}><td>{c.label}{c.unit && ` (${c.unit})`}</td>
                      <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}><span className={x.cls}>{x.text}</span></td>
                      <td className="en" style={{ margin: 0 }}>{strength(c, its)}</td>
                      <td><span className={x.state === 'assume' ? 'c-blue' : x.state === 'empty' ? 'c-ora' : ''}>
                        {x.state === 'assume' ? '팀 가정' : x.state === 'empty' ? '비어 있음 · 판정 때 확인 필요' : '카탈로그'}</span>
                        <div className="en" style={{ margin: 0 }}>{x.state === 'assume' ? p.comparison_values_source ?? '팀 가정' : p.source_doc}</div></td></tr>
                  })}</tbody>
                </table>
                <div className="pnote">판정 {p.used}건 · 검토 {p.used_runs}건에 사용됨. 값이 없는 칸은 판정에서 "확인 필요"가 됩니다.</div>
              </>}
              {tab === 'phys' && (
                <table className="tbl"><thead><tr><th>항목</th><th>값</th><th>근거</th></tr></thead>
                  <tbody>
                    {(() => { const x = cell(p, 'weight_kg'); const c = COLS.find((k) => k.key === 'weight_kg')!
                      return <tr><td>{c.label} ({c.unit})</td><td><span className={x.cls}>{x.text}</span></td><td>{x.state === 'ok' ? p.source_doc : x.state === 'empty' ? '비어 있음' : '해당 없음'}</td></tr> })()}
                    <tr><td>치수 · 운송 중량</td><td><span className="dimv">—</span></td><td className="dimv">제품표에 없음</td></tr>
                  </tbody></table>
              )}
              {tab === 'hist' && <>
                <div className="lbl" style={{ marginTop: 0 }}>지금 쓰이는 검토 {p.used_runs}</div>
                {!uses.length && <p className="pnote">진행 중인 검토에 쓰이지 않습니다.</p>}
                {uses.map((u) => {
                  const d = dday(u.due_date)
                  return <a key={u.run_id} className="qv-u" href={href(`/reviews/${u.run_id}`)}><span className="mono">{u.review_no}</span>
                    <span className="nm">{u.review_name ?? '이름 없음'}<small>판정 {u.n} · {resultCounts(u)}</small></span>{d && <span className={`dd${d.late ? ' red' : ''}`}>{d.text}</span>}</a>
                })}
                <div className="lbl">자주 나온 판정</div>
                {hist.length ? <ul className="hl">{hist.map(([k, n]) => <li key={k}><span>{RESULT_NAMES[k] ?? k}</span><b className={RESULT_TONES[k]}>{n}</b></li>)}</ul>
                  : <p className="pnote">검토에서 쓰인 기록이 없습니다.</p>}
                <button type="button" className="tgl" onClick={() => setBids(!bids)} aria-expanded={bids}>
                  <span className="ms" aria-hidden="true">{bids ? 'expand_less' : 'expand_more'}</span><b>최근 입찰 결과</b><span className="tgs">예시</span></button>
                {bids && <><ExampleBand /><p className="pnote">입찰 결과는 이 시스템 범위 밖이라 예시입니다. 금액·경쟁사는 보이지 않습니다.</p></>}
              </>}
              {tab === 'field' && (p.field_history.length ? (
                <table className="tbl"><thead><tr><th>사례</th><th>현상</th><th>원인</th><th>조치</th><th>관련 판정 항목</th></tr></thead>
                  <tbody>{p.field_history.map((f) => <tr key={f.fault_link_id}><td style={{ whiteSpace: 'nowrap' }}><b>{f.fault_id}</b>
                    <div className="en" style={{ margin: 0 }}>해결 사례 {f.cases}건 · {f.confirmed_by}</div></td><td>{f.symptom}</td><td>{f.root_cause ?? '—'}</td><td>{f.action ?? '—'}</td>
                    <td><span className="tag" style={{ margin: 0 }}>{f.item_name}</span></td></tr>)}</tbody></table>
              ) : <p className="pnote">연결된 고장 사례가 없습니다.</p>)}
            </div>
          </section>
        </div>
      </div>
    </main>
  )
}

/** 제품 계열 대표 사진과 출처 (add-product-photos). 모델마다 다른 사진이 아니라서 그렇게 적는다. */
function Photo({ sourceDoc }: { sourceDoc: string | null }) {
  const ph = productPhoto(sourceDoc)
  if (!ph) return <figure className="pimg" aria-label="제품 사진"><figcaption>공식 사진 없음</figcaption></figure>
  return (
    <figure className="pimg" aria-label="제품 사진">
      <img src={ph.src} alt={`${ph.family} 대표 사진`} style={{ display: 'block', width: '100%', height: 180, objectFit: 'contain' }} />
      <figcaption>{ph.family} 대표 사진 · 이 모델만의 사진은 아님<br />
        사진 출처: <a href={ph.page} target="_blank" rel="noreferrer">{ph.site}</a></figcaption>
    </figure>
  )
}

const DOC_SHOW = 5
/** 문서 탭 (add-product-docs): 공식 자료실의 카탈로그·매뉴얼·시험 성적서·인증서 링크. 종류마다 5건까지, 나머지는 펼쳐 본다. */
function Docs({ sourceDoc }: { sourceDoc: string | null }) {
  const d = productDocs(sourceDoc)
  const [open, setOpen] = useState<Record<string, boolean>>({})
  if (!d) return <p className="en" style={{ margin: 0 }}>공식 자료실 문서 없음</p>
  return (
    <div className="pvdocs" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <p className="en" style={{ margin: 0 }}>
        LS ELECTRIC 공식 자료실 문서 ({d.retrieved} 기준). 제품 계열 공통 문서라 이 모델에 해당하는지는 문서에서 확인하세요. <a href={d.page} target="_blank" rel="noreferrer">공식 페이지</a>
      </p>
      {DOC_KINDS.map(([kind, label]) => {
        const list = d.docs.filter((x) => x.kind === kind)
        const shown = open[kind] ? list : list.slice(0, DOC_SHOW)
        return (
          <div key={kind} className="g-group doc-group" aria-label={label}>
            <div className="g-head">{label}<span className="g-n">{list.length}</span></div>
            {!list.length && <div className="g-item none"><span>공식 자료실에 없음</span></div>}
            {shown.map((x) => (
              <a key={x.url} className="g-item" href={x.url} target="_blank" rel="noreferrer">
                <span style={{ fontWeight: 600 }}>{x.title}{isSourceCatalog(x, sourceDoc) && <span className="c-green"> · 제품표 값의 출처</span>}</span>
                <span className="en" style={{ margin: 0 }}>{[x.date, x.lang, x.org].filter(Boolean).join(' · ')}</span>
              </a>
            ))}
            {list.length > DOC_SHOW && (
              <button type="button" className="g-more" style={{ background: 'none', border: 0, cursor: 'pointer', textAlign: 'left' }}
                onClick={() => setOpen({ ...open, [kind]: !open[kind] })}>{open[kind] ? '접기' : `외 ${list.length - DOC_SHOW}건 더 보기`}</button>
            )}
          </div>
        )
      })}
    </div>
  )
}

