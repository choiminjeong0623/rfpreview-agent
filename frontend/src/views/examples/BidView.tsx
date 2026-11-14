import { useState } from 'react'
import { EXAMPLE_BIDS, RESULTS, type Bid } from '../../examples/SCR-14'
import { EXAMPLE_BID_DETAILS } from '../../examples/SCR-15'
import { usePageCss } from '../../shell/pageCss'
import { href } from '../../shell/router'
import { ExampleBand } from '../detail/ExampleTab'

// SCR-15 입찰 상세 (목업 v4.57 BidView). docs/screens/SCR-15-입찰상세.md
// 입찰 결과 API가 없어 예시 데이터로만 보여 준다. 금액·가격 평가는 영업 권한이 있어야 보인다.

type Tab = 'res' | 'rel' | 'doc' | 'hist'
const TABS: [Tab, string][] = [['res', '결과·평가'], ['rel', '관련 입찰'], ['doc', '문서'], ['hist', '이력']]
const KINDS = ['일탈', '질의', '강점', '작성', '조건', '확인']
const ORDER = [...EXAMPLE_BIDS].sort((p, q) => (p.sub < q.sub ? 1 : -1))
const short = (v: string) => (v.startsWith('2026') ? v.slice(5) : v.slice(2))
const LOCK = <span className="lock" title="영업 권한 필요"><span className="ms" aria-hidden="true">lock</span>영업 권한</span>

function summary(list: Bid[]) {
  return (Object.keys(RESULTS) as Bid['res'][]).map((k) => [RESULTS[k][0], list.filter((x) => x.res === k).length] as const)
    .filter(([, n]) => n).map(([label, n]) => `${label} ${n}`).join(' · ')
}

function Related({ title, list, me }: { title: string; list: Bid[]; me: Bid }) {
  return (
    <section className="fcard"><h2>{title}<span className="note">{summary(list)}</span></h2>
      {list.length ? (
        <ul className="bvl">{list.map((x) => (
          <li key={x.bid}><span className={`st ${RESULTS[x.res][1]}`}>{RESULTS[x.res][0]}</span>
            <span className="tx"><a href={href(`/bids/${x.bid}`)}>{x.name}</a>
              <span>{x.bid} · {short(x.sub)} · {x.cust === me.cust ? x.prod : x.cust}</span></span></li>
        ))}</ul>
      ) : <p className="bvempty">다른 입찰이 없습니다.</p>}
    </section>
  )
}

export function BidView({ bid: b }: { bid: Bid }) {
  usePageCss('BidView')
  const [tab, setTab] = useState<Tab>('res')
  const [asked, setAsked] = useState(false)
  const [toast, setToast] = useState('')
  const d = EXAMPLE_BID_DETAILS[b.bid]
  const ix = ORDER.findIndex((x) => x.bid === b.bid)
  const prev = ORDER[ix - 1]
  const next = ORDER[ix + 1]
  const sameC = ORDER.filter((x) => x.cust === b.cust && x.bid !== b.bid)
  const sameP = ORDER.filter((x) => x.prod === b.prod && x.bid !== b.bid)
  const kinds = (k: string) => d.rows.filter((r) => r[0] === k).length
  const acc = d.rows.filter((r) => r[5] === 'green').length
  const rej = d.rows.filter((r) => r[5] === 'red').length
  const rowSum = d.rows.length
    ? KINDS.filter((k) => kinds(k)).map((k) => `${k} ${kinds(k)}`).join(' · ')
      + (b.res === 'win' || b.res === 'lose' ? ` · 수용·가점 ${acc}${rej ? ` · 거절·감점 ${rej}` : ''}` : '')
    : ''
  const why = b.why === '—' ? (b.res === 'win' ? '수주' : b.res === 'wait' ? '개찰 전' : b.why) : b.why
  const noDeb = b.res === 'wait' ? '개찰 뒤에 받을 수 있습니다.' : b.res === 'void' ? '유찰되어 평가 의견이 없습니다.' : '고객에게서 평가 의견을 받지 못했습니다.'
  const ask = () => {
    setAsked(true)
    setToast('영업 담당에게 평가 의견 확보를 요청했습니다. (예시 화면이라 실제로 보내지 않습니다)')
    setTimeout(() => setToast(''), 3000)
  }

  return (
    <main className="main">
      <ExampleBand />
      <div className="fh" style={{ marginTop: 4 }}><h1>{b.name}</h1>
        <div className="bvnav">
          <a className={prev ? '' : 'dis'} href={prev ? href(`/bids/${prev.bid}`) : undefined} aria-disabled={!prev || undefined}>
            <span className="ms" aria-hidden="true" style={{ fontSize: 18 }}>chevron_left</span>이전 입찰</a>
          <a className={next ? '' : 'dis'} href={next ? href(`/bids/${next.bid}`) : undefined} aria-disabled={!next || undefined}>
            다음 입찰<span className="ms" aria-hidden="true" style={{ fontSize: 18 }}>chevron_right</span></a>
        </div>
      </div>

      <div className="bvk">
        {d.ev.map(([k, v, c]) => <div key={k}><span className="l">{k}</span><b className={c === 'lock' ? '' : c}>{c === 'lock' ? LOCK : v}</b></div>)}
        <div><span className="l">금액</span><b>{LOCK}</b></div>
      </div>

      <div className="fgrid">
        <div style={{ minWidth: 0 }}>
          <div className="bvpanel">
            <nav className="bvtabs" role="tablist" aria-label="입찰 상세">
              {TABS.map(([k, label]) => (
                <button key={k} type="button" role="tab" className={tab === k ? 'on' : ''} aria-selected={tab === k} onClick={() => setTab(k)}>{label}</button>
              ))}
            </nav>
            {tab === 'res' && (
              <>
                <section className="fcard"><h2>결과 사유{b.rsn && <span className="bvk2">{b.rsn}</span>}</h2>
                  <p className="bvwhy">{why}</p>
                  <p className="bvmemo">{b.memo}<span className="by">입력 {d.memoBy}</span></p>
                </section>
                <section className="fcard"><h2>일탈·질의와 고객 반응<span className="note">{rowSum}</span></h2>
                  {d.rows.length ? (
                    <div className="bvtw"><table className="bvt">
                      <thead><tr><th style={{ width: 64 }}>구분</th><th>항목</th><th>고객 요구</th><th>우리 제안</th><th>고객 반응</th></tr></thead>
                      <tbody>{d.rows.map(([kind, item, req, ours, rx, c]) => (
                        <tr key={kind + item}><td><span className="bvk2">{kind}</span></td><td style={{ fontWeight: 600 }}>{item}</td>
                          <td style={{ whiteSpace: 'nowrap' }}>{req}</td><td>{ours}</td><td><span className={`rx ${c}`}>{rx}</span></td></tr>
                      ))}</tbody>
                    </table></div>
                  ) : <p className="bvempty">일탈과 질의 없이 요구사항을 모두 그대로 충족해 제출했습니다.</p>}
                </section>
                <section className="fcard"><h2>고객 평가 의견</h2>
                  {d.deb ? (
                    <>
                      <div className="bvdeb"><span className="lbl">{b.country === '한국' ? '원문' : '원문 (영어)'}</span>{d.deb[0]}</div>
                      {d.deb[1] && <div className="bvdeb"><span className="lbl">번역 (한국어)</span>{d.deb[1]}</div>}
                    </>
                  ) : (
                    <div className="bvempty"><span>{noDeb}</span>
                      {(b.res === 'win' || b.res === 'lose') && <button type="button" className="bo" onClick={ask} disabled={asked}>{asked ? '요청함' : '영업 담당에게 요청'}</button>}</div>
                  )}
                </section>
              </>
            )}
            {tab === 'rel' && (
              <>
                <section className="fcard"><h2>이 입찰을 참고하는 판정</h2>
                  {d.ref.length ? (
                    <ul className="bvl">{d.ref.map(([rv, item, st]) => (
                      <li key={rv + item}><span className="tx"><a href={href('/reviews')} title="예시 검토 번호라 실제 검토가 없습니다. 검토 목록으로 갑니다">{item}</a><span>{rv} · {st}</span></span></li>
                    ))}</ul>
                  ) : <p className="bvempty">진행 중인 검토에서 참고한 판정이 없습니다.</p>}
                </section>
                <div className="bvrel">
                  <div style={{ minWidth: 0 }}><Related title="같은 고객의 입찰" list={sameC} me={b} /></div>
                  <div style={{ minWidth: 0 }}><Related title="같은 제품의 입찰" list={sameP} me={b} /></div>
                </div>
              </>
            )}
            {tab === 'doc' && (
              <div className="bvrel bvdocs">
                {([['우리가 제출한 문서', d.mine], ['고객 문서', d.cust]] as const).map(([title, docs]) => (
                  <section key={title} className="fcard"><h2>{title}</h2><ul className="ffiles">{docs.map(([n, k]) => (
                    <li key={n}><span className="ms" aria-hidden="true">description</span><span className="nm">{n}<span className="sub3">{k}</span></span></li>
                  ))}</ul></section>
                ))}
              </div>
            )}
            {tab === 'hist' && (
              <section className="fcard"><h2>이력</h2>
                <ul className="ftl">{d.hist.map(([t, x, w]) => (
                  <li key={t + x} style={{ gridTemplateColumns: '78px 1fr' }}><span className="t">{short(t)}</span><span>{x}<span style={{ color: 'var(--c-muted)' }}> · {w}</span></span></li>
                ))}</ul>
              </section>
            )}
          </div>
        </div>
        <aside style={{ minWidth: 0 }}>
          <section className="fcard"><h2>기본 정보</h2>
            <dl className="bvinfo">
              <dt>입찰 번호</dt><dd>{b.bid}</dd><dt>제출일</dt><dd>{b.sub}</dd>
              <dt>결과 통보</dt><dd>{d.rdate || (b.res === 'wait' ? '개찰 11-05 예정' : '—')}</dd>
              <dt>연결 검토</dt><dd><a href={href('/reviews')} title="예시 검토 번호라 실제 검토가 없습니다. 검토 목록으로 갑니다">{b.rv}</a></dd>
              <dt>담당 엔지니어</dt><dd>기술 검토 엔지니어</dd><dt>영업 담당</dt><dd>영업 담당</dd>
              <dt>고객사</dt><dd>{b.cust}</dd><dt>최종 발주처</dt><dd>{d.end}</dd><dt>국가</dt><dd>{b.country}</dd>
              <dt>사용 제품</dt><dd><a href={href('/products')}>{b.prod}</a></dd><dt>평가 방식</dt><dd>{d.method}</dd>
            </dl>
          </section>
        </aside>
      </div>
      {toast && <div className="ftoast" role="status"><span className="ms" aria-hidden="true">check_circle</span>{toast}</div>}
    </main>
  )
}
