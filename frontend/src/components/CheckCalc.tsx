import { useEffect, useState } from 'react'
import { api, type EngineeringCheck, type PeakCheck } from '../api'
import { CHECK_NAMES, CHECK_TONES, CHECK_RULE } from './checks'

// 판정 상세 "검산 확인" 상자 (add-check-calculator, FR-12). 계산은 서버의 분석 검산과 같은 코드가 한다 (CR-01).
// 값을 바꿔 보는 참고 계산이라 판정·기록은 바뀌지 않는다. 단위는 kA만 받고 바꾸지 않는다 (CR-10).

const kas = (n: number) => `${Number(n.toFixed(2))} kA`

export function CheckCalc({ check }: { check: EngineeringCheck }) {
  const start = { ik: String(check.ik_ka), hz: String(check.frequency_hz ?? 50), peak: String(check.peak_ka) }
  const [v, setV] = useState(start)
  const [out, setOut] = useState<PeakCheck | null>(null)
  const [error, setError] = useState<string | null>(null)
  const nums = [Number(v.ik), Number(v.hz), Number(v.peak)]
  const valid = nums.every((n) => Number.isFinite(n) && n > 0)
  useEffect(() => {
    if (!valid) return
    const t = setTimeout(() => {
      api.peakCheck(nums[0], nums[1], nums[2]).then((r) => { setOut(r); setError(null) }, (e: Error) => setError(e.message))
    }, 300)
    return () => clearTimeout(t)
  }, [v.ik, v.hz, v.peak, valid])   // eslint-disable-line react-hooks/exhaustive-deps
  const changed = v.ik !== start.ik || v.hz !== start.hz || v.peak !== start.peak
  const field = (k: 'ik' | 'peak', label: string) => (
    <label className="cc-f"><span>{label}</span>
      <span className="cc-in"><input className="fi" inputMode="decimal" value={v[k]} aria-label={label}
        onChange={(e) => setV({ ...v, [k]: e.target.value })} /> kA</span></label>
  )
  return (
    <section className="cc" aria-label="검산 확인">
      <div className="cc-h"><b>검산 확인</b><span>참고 계산 · 판정은 바뀌지 않습니다</span></div>
      <div className="cc-row">
        {field('ik', '단시간 전류')}
        <label className="cc-f"><span>주파수</span>
          <select className="fi" aria-label="주파수" value={v.hz} onChange={(e) => setV({ ...v, hz: e.target.value })}>
            <option value="50">50 Hz</option><option value="60">60 Hz</option></select></label>
        {field('peak', '최대 순간 전류')}
        <button type="button" className="lnk" disabled={!changed} onClick={() => setV(start)}>원문 값으로</button>
      </div>
      {!valid && <p className="c-red cc-o">0보다 큰 숫자를 넣어 주세요.</p>}
      {valid && error && <p className="c-red cc-o" role="alert">{error}</p>}
      {valid && !error && out && (
        <p className="cc-o" role="status">
          <span className={CHECK_TONES[out.result]}>{CHECK_NAMES[out.result]}</span>{' '}
          {out.factor !== null && out.expected_ka !== null
            ? <>{kas(nums[0])} × {out.factor} = <b>{kas(out.expected_ka)}</b>
              <span className="en" style={{ display: 'inline', marginLeft: 8 }}>같다고 보는 값 {out.allowed_ka.map(kas).join(' · ')}</span></>
            : '50·60 Hz가 아니어서 배수가 없습니다'}
        </p>
      )}
      <p className="en cc-r">{CHECK_RULE} · 규격 표준값(R10)·정수 반올림까지 같다고 봅니다</p>
    </section>
  )
}
