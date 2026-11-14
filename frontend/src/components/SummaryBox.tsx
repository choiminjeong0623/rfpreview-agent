import { useCallback, useEffect, useRef, useState } from 'react'
import type { ScreenSummary } from '../api'
import { href } from '../shell/router'
import '../mockup/SummaryV496.css'

// 요약 상자 (SCR-00 5장, 목업 v4.96 .ais, change add-screen-summary). 검토 상세·홈만 (결정 Q1).
// 문장은 백엔드가 틀에 채운다(AI 없음). 이름은 "요약", 꼬리표 "코드가 씀".

const hhmm = (iso: string) => {
  const d = new Date(iso)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

/** load가 바뀌면(deps) 조용히 다시 부르고, [다시 요약]을 누르면 회색 줄을 보이며 다시 부른다 */
export function SummaryBox({ load, label }: { load: () => Promise<ScreenSummary>; label: string }) {
  const [data, setData] = useState<ScreenSummary | null>(null)
  const [failed, setFailed] = useState(false)
  const [busy, setBusy] = useState(true)
  const [round, setRound] = useState(0)             // 다시 요약할 때마다 문장 나타남을 다시 보인다
  const seq = useRef(0)
  const fetch = useCallback((loud: boolean) => {
    const mine = ++seq.current
    load().then((d) => {
      if (!Array.isArray(d?.sentences)) throw new Error('요약을 불러오지 못했습니다')   // 문장 없는 응답은 실패로 보인다
      return d
    }).then((d) => { if (mine === seq.current) { setData(d); setFailed(false); setBusy(false); if (loud) setRound((r) => r + 1) } },
      () => { if (mine === seq.current) { setFailed(true); setBusy(false) } })
  }, [load])
  useEffect(() => fetch(false), [fetch])            // 데이터가 바뀌면 조용히 다시 부른다
  const again = () => { setBusy(true); fetch(true) }
  return (
    <section className="ais" aria-label={label} aria-live="polite" aria-busy={busy}>
      <span className="ais-ic" aria-hidden="true"><span className="ms">summarize</span></span>
      <div className="ais-b">
        <div className="ais-h"><b>요약</b><span className="ais-tag" title="시스템이 정해진 양식으로 만든 요약입니다 (AI 미사용)">자동 요약</span>
          {data && !failed && <span className="ais-t">{hhmm(data.made_at)} 요약</span>}
          {data?.meta && !failed && <span className="ais-m">· {data.meta}</span>}
          <button type="button" onClick={again} disabled={busy}><span className="ms" aria-hidden="true">refresh</span>다시 요약</button></div>
        {busy && <div className="ais-sk" aria-label="요약을 쓰는 중"><i /><i /></div>}
        {failed && !busy && <p className="ais-err" role="alert">요약을 만들지 못했습니다 · [다시 요약]을 눌러 주세요.</p>}
        {data && !busy && !failed && (
          <p className="ais-p" key={round}>
            {data.sentences.map((s, i) => (
              <span key={i} className="sn" style={{ animationDelay: `${0.35 + i * 0.45}s` }}>
                {s.map((p, j) => p.kind === 'link' && p.href
                  ? <a key={j} href={href(p.href)}>{p.t}</a>
                  : p.kind === 'strong' ? <span key={j} className="rd">{p.t}</span> : <span key={j}>{p.t}</span>)}{' '}
              </span>
            ))}
          </p>
        )}
      </div>
    </section>
  )
}
