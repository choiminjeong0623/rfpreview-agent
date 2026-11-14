import { useState } from 'react'
import { Pager } from '../../components/Pager'
import { EXAMPLE_BIDS, RESULTS, type Bid, type BidResult } from '../../examples/SCR-14'
import { usePageCss } from '../../shell/pageCss'
import { href } from '../../shell/router'
import { ExampleBand } from '../detail/ExampleTab'
import { useFakeLoad } from './useFakeLoad'

// SCR-14 입찰 이력 (목업 v4.57 Bids). docs/screens/SCR-14-입찰이력.md
// 입찰 결과·금액 API가 없어 예시 데이터로만 보여 준다. 금액·경쟁사는 영업 권한이 있어야 보인다 (가격은 범위 밖).

type Period = '1m' | '3m' | 'all'
const PERIODS: [Period, string][] = [['1m', '1개월'], ['3m', '3개월'], ['all', '전체']]
const FROM: Record<Period, string> = { '1m': '2026-09-24', '3m': '2026-07-24', all: '0000' }
const PRODUCTS = Array.from(new Set(EXAMPLE_BIDS.map((b) => b.prod))).sort()
const subText = (sub: string) => (sub.startsWith('2026') ? sub.slice(5) : sub.slice(2))

function count(list: Bid[], key: (b: Bid) => string) {
  const out: Record<string, number> = {}
  list.forEach((b) => { const k = key(b); out[k] = (out[k] ?? 0) + 1 })
  return Object.entries(out).sort((a, b) => b[1] - a[1])
}

export function Bids() {
  usePageCss('Bids')
  const [period, setPeriod] = useState<Period>('all')
  const [q, setQ] = useState('')
  const [prod, setProd] = useState('all')
  const [res, setRes] = useState<'all' | BidResult>('all')
  const [page, setPage] = useState(1)
  const [size, setSize] = useState(10)
  const loader = useFakeLoad()

  const needle = q.trim().toLowerCase()
  const found = EXAMPLE_BIDS.filter((b) => b.sub >= FROM[period])
    .filter((b) => prod === 'all' || b.prod === prod)
    .filter((b) => res === 'all' || b.res === res)
    .filter((b) => !needle || (b.name + b.cust + b.rv + b.bid).toLowerCase().includes(needle))
    .sort((a, b) => (a.sub < b.sub ? 1 : a.sub > b.sub ? -1 : 0))
  const pages = Math.max(1, Math.ceil(found.length / size))
  const cur = Math.min(page, pages)
  const rows = found.slice((cur - 1) * size, cur * size)
  // 요약은 제품 필터만 따른다 (목업과 같음)
  const base = EXAMPLE_BIDS.filter((b) => prod === 'all' || b.prod === prod)
  const n = (r: BidResult) => base.filter((b) => b.res === r).length
  const done = n('win') + n('lose')
  const reasons = count(base.filter((b) => b.rsn), (b) => b.rsn)
  const tech = count(base.filter((b) => b.rsn === '기술'), (b) => b.why.replace('기술: ', '')).slice(0, 2)
  const techTop = tech.length ? tech : [['없음', 0] as [string, number]]
  const filtered = !!q || prod !== 'all' || res !== 'all'
  const exportAll = () => loader.start('내보내기',
    [[0, `입찰 ${found.length}건 정리 중`], [45, '결과·사유 붙이는 중'], [75, 'Excel 파일 만드는 중']],
    '예시 화면이라 파일은 만들지 않았습니다. 실제 파일에서도 금액은 영업 권한이 없어 빠집니다.')

  return (
    <main className="main">
      <ExampleBand />
      <div className="ttl">
        <h1>입찰 이력</h1>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <div className="seg" role="group" aria-label="기간">
            {PERIODS.map(([k, label]) => (
              <button key={k} type="button" className={period === k ? 'on' : ''} onClick={() => { setPeriod(k); setPage(1) }}>{label}</button>
            ))}
          </div>
          <button type="button" className="bo" onClick={exportAll}><span className="ms" aria-hidden="true" style={{ fontSize: 'var(--ic-s)' }}>download</span>내보내기</button>
        </div>
      </div>
      <div className="bsum">
        <div><span className="l">수주율</span><b>{done ? `${Math.round((n('win') / done) * 100)} %` : '—'}</b><span className="s">결과가 나온 {done}건 기준</span></div>
        <div><span className="l">결과</span><b>{n('win')}<span style={{ fontSize: 'var(--fs-sm)', fontWeight: 400, color: 'var(--c-muted)' }}> 수주 · {n('lose')} 실주 · {n('void')} 유찰</span></b><span className="s">결과 대기 {n('wait')}건</span></div>
        <div><span className="l">실주 사유</span><ul className="rsn">{reasons.map(([k, v]) => <li key={k}><span>{k}</span><b>{v}건</b></li>)}</ul></div>
        <div><span className="l">기술 사유로 실주한 요구</span><ul className="rsn">{techTop.map(([k, v]) => <li key={k}><span>{k}</span><b className="c-red">{v}건</b></li>)}</ul></div>
      </div>
      <section className="sec">
        <div className="sech">
          <h2>입찰 <span style={{ fontWeight: 400, color: 'var(--c-muted)' }}>{found.length}</span></h2>
          <span className="lock"><span className="ms" aria-hidden="true">lock</span>금액·경쟁사는 영업 권한이 있어야 보임</span>
        </div>
        <div className="filters" role="search">
          <label htmlFor="bq" className="sr">입찰 검색</label>
          <input className="fi" id="bq" value={q} onChange={(e) => { setQ(e.target.value); setPage(1) }} placeholder="입찰명, 고객, 검토 번호" style={{ flex: '1 1 220px', maxWidth: 280 }} />
          <label htmlFor="bp" className="sr">제품</label>
          <select className="fi" id="bp" value={prod} onChange={(e) => { setProd(e.target.value); setPage(1) }}>
            <option value="all">모든 제품</option>
            {PRODUCTS.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
          <label htmlFor="br" className="sr">결과</label>
          <select className="fi" id="br" value={res} onChange={(e) => { setRes(e.target.value as 'all' | BidResult); setPage(1) }}>
            <option value="all">모든 결과</option>
            {(Object.keys(RESULTS) as BidResult[]).map((k) => <option key={k} value={k}>{RESULTS[k][0]}</option>)}
          </select>
          {filtered && <button type="button" className="bo" onClick={() => { setQ(''); setProd('all'); setRes('all'); setPage(1) }}>필터 지우기</button>}
        </div>
        <div className="tw">
          <table className="tbl">
            <thead><tr>
              <th style={{ width: '34%' }}>입찰</th><th>고객 · 국가</th><th>제출</th><th>사용 제품</th><th className="num">일탈</th><th>결과</th><th>결과 사유</th><th className="num">금액</th>
            </tr></thead>
            <tbody>{rows.map((b) => (
              <tr key={b.bid} className="rlk" title="입찰 상세 보기">
                <td><a className="rowlink" href={href(`/bids/${b.bid}`)}>{b.name}</a>
                  <div className="cond meta"><span>{b.bid}</span><a className="rvlink" href={href('/reviews')} title="예시 검토 번호라 실제 검토가 없습니다. 검토 목록으로 갑니다">{b.rv}</a></div></td>
                <td>{b.cust}<div className="cond">{b.country}</div></td>
                <td style={{ whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums' }}>{subText(b.sub)}</td>
                <td style={{ whiteSpace: 'nowrap' }}>{b.prod}</td>
                <td className="num"><span className={b.dev ? 'neg' : 'dimv'}>{b.dev}</span></td>
                <td><span className={`st ${RESULTS[b.res][1]}`}>{RESULTS[b.res][0]}</span></td>
                <td>{b.why}</td>
                <td className="num"><span className="lock" title="영업 권한 필요"><span className="ms" aria-hidden="true">lock</span><span className="sr">영업 권한 필요</span></span></td>
              </tr>
            ))}</tbody>
          </table>
          <Pager total={found.length} page={cur} size={size} shown={rows.length} onPage={setPage} onSize={(v) => { setSize(v); setPage(1) }} />
        </div>
        {found.length === 0 && <p style={{ margin: 0, padding: '16px 12px', color: 'var(--c-muted)' }}>조건에 맞는 입찰이 없습니다.</p>}
      </section>
      {loader.view}
    </main>
  )
}
