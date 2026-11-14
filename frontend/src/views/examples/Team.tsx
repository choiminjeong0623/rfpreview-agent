import { useState } from 'react'
import { EXAMPLE_HELP, EXAMPLE_TEAM } from '../../examples/SCR-20'
import { usePageCss } from '../../shell/pageCss'
import { href } from '../../shell/router'
import { ExampleBand } from '../detail/ExampleTab'

// SCR-20 팀 현황 (목업 v4.57 Team). docs/screens/SCR-20-팀현황.md
// 팀원별 진행·접속 상태·도움 요청 API가 없어 예시 데이터로만 보여 준다.

const SEG_CLS = ['s1', 's2', 's3', 's4', 's5']
const SEG_NAMES = ['분석 중', '판정 확인', '협조 대기', '결재 대기', '제출 준비']
const sum = (xs: number[]) => xs.reduce((a, b) => a + b, 0)

export function Team() {
  usePageCss('Team')
  const [replied, setReplied] = useState<Record<number, boolean>>({})
  const [toast, setToast] = useState('')
  const reply = (i: number, who: string) => {
    setReplied({ ...replied, [i]: true })
    setToast(`의견을 남겼습니다. ${who}에게 알림이 갑니다. (예시 화면이라 실제로 보내지 않습니다)`)
    setTimeout(() => setToast(''), 2800)
  }

  return (
    <main className="main">
      <ExampleBand />
      <div className="ttl"><h1>팀 현황</h1><span className="sh-mut">전력기기사업부 기술검토팀 · 6명 · 10-24 (토) 기준</span></div>
      <div className="sh-sum">
        <span>진행 중 검토<b>{sum(EXAMPLE_TEAM.map((m) => sum(m[4])))}</b></span>
        <span>3일 내 마감<b className="c-red">{sum(EXAMPLE_TEAM.map((m) => m[5]))}</b></span>
        <span>마감 경과<b className="c-red">{sum(EXAMPLE_TEAM.map((m) => m[6]))}</b></span>
        <span>도움 요청<b className="c-ora">{EXAMPLE_HELP.filter((_, i) => !replied[i]).length}</b></span>
        <span>지금 접속<b>{EXAMPLE_TEAM.filter((m) => m[2]).length}명</b></span>
      </div>
      <section className="sec" aria-labelledby="tmT">
        <div className="sech"><h2 id="tmT">팀원별 진행 현황</h2><span className="sh-mut">줄을 누르면 그 사람의 검토 목록으로 이동합니다</span></div>
        <div className="sh-box" style={{ marginTop: 12 }}>
          <div className="tm-tr sh-th"><span>팀원</span><span>진행 중</span><span>단계별 (분석 · 판정 · 협조 · 결재 · 제출)</span><span>3일 내 마감</span><span>마감 경과</span><span>그 밖의 일 · 부재</span><span /></div>
          {EXAMPLE_TEAM.map(([name, role, on, st, seg, soon, over, help, away, other]) => {
            const n = sum(seg)
            return (
              <a key={name} className="tm-tr tm-row" href={href('/reviews')}>
                <span className="hm-who"><span className="hm-av" aria-hidden="true">{name[0]}<i className={on ? 'on' : ''} /></span><span className="hm-nm"><b>{name}</b><span>{role} · {st}</span></span></span>
                <span className="tm-big">{n}<small>건</small></span>
                <span className="tm-stk"><span className="tm-bar">{seg.map((v, i) => (
                  <i key={i} className={SEG_CLS[i]} style={{ width: `${n ? (v / n) * 100 : 0}%` }} title={`${SEG_NAMES[i]} ${v}건`} />
                ))}</span><span className="sh-mut mono">{seg.join(' · ')}</span></span>
                <span className={`mono ${soon ? 'c-red' : 'sh-mut'}`}>{soon ? `${soon}건` : '—'}</span>
                <span className={`mono ${over ? 'c-red' : 'sh-mut'}`}>{over ? `${over}건` : '—'}</span>
                <span className="tm-oth"><span>{other || (n ? '' : '진행 중인 검토 없음')}</span>
                  {away !== '—' && <span className="tm-away"><span className="ms" aria-hidden="true">event_busy</span>{away}</span>}
                  {help > 0 && <span className="hm-help"><span className="ms" aria-hidden="true">front_hand</span>도움 요청 {help}건</span>}</span>
                <span className="ms" aria-hidden="true" style={{ color: 'var(--c-disabled)' }}>chevron_right</span>
              </a>
            )
          })}
        </div>
        <div className="tm-lg">{SEG_NAMES.map((label, i) => <span key={label}><i className={SEG_CLS[i]} />{label}</span>)}</div>
      </section>
      <section className="sec" aria-labelledby="hpT">
        <div className="sech"><h2 id="hpT">도움 요청</h2></div>
        <div className="sh-box" style={{ marginTop: 12 }}>
          {EXAMPLE_HELP.map(([who, ref, ask, t], i) => (
            <div key={ref} className="tm-help">
              <span className="ms" aria-hidden="true" style={{ color: 'var(--c-orange)' }}>front_hand</span>
              <div className="tm-hb"><b>{ref}</b><span>{ask}</span><span className="sh-mut">{who} · {t}</span></div>
              {replied[i] && <span className="st c-green">의견 남김</span>}
              <a className="bo" href={href('/reviews')}>검토 열람</a>
              <button type="button" className="bp" onClick={() => reply(i, who)} disabled={replied[i]}>의견 남기기</button>
            </div>
          ))}
        </div>
        <div className="sh-note"><span className="ms" aria-hidden="true">lock</span><span>다른 사람의 검토는 열람만 할 수 있고 의견은 댓글로 남깁니다. 담당자 변경과 대리인 지정은 팀장만 할 수 있으며 검토 이력에 남습니다.</span></div>
      </section>
      {toast && <div className="stt" role="status"><span className="ms" aria-hidden="true">check_circle</span>{toast}</div>}
    </main>
  )
}
