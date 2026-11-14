import { useEffect, useRef, useState } from 'react'
import { api, type RunListItem } from '../api'
import { duration, progress, STALL_MS, stepText } from '../components/progress'
import { useLoad, useRepeat } from '../components/useLoad'
import { useToast } from '../ui'
import { href, useHashPath } from './router'

// 머리글 분석 진행 표시 (SCR-00 v4.96 4장, 목업 v4.60 .anb·.anp). change update-header-progress.
// 주소가 바뀔 때 GET /runs를 한 번 부르고, 처리 중 검토가 있는 동안만 5초마다 다시 부른다.
// 앞선 응답에서 처리 중이던 검토가 끝나면 알림 쌓기로 알린다. 처음 응답에서 이미 끝난 검토는 알리지 않는다.

const busy = (r: RunListItem) => r.stage === 'PROCESSING'
const nameOf = (r: RunListItem) => r.review_name ?? r.files ?? r.review_no
// 사람이 취소한 검토는 처리 실패로 남고 오류 문장이 이렇게 끝난다 (pipeline/run.py cancel_message)
const cancelled = (r: RunListItem) => r.stage === 'FAILED' && Boolean(r.error_message?.endsWith('분석을 취소했습니다.'))

export function AnalysisProgress({ open, onToggle, onClose }: { open: boolean; onToggle: () => void; onClose: () => void }) {
  const path = useHashPath()
  // 불러오지 못하면 단추를 숨긴다 (머리글은 오류를 띄우지 않는다. 화면마다 자기 오류를 보인다)
  const { data, reload } = useLoad(() => api.runs(), [path])
  const active = (data ?? []).filter(busy)
  useRepeat(active.length > 0, reload)
  const toast = useToast()
  const seen = useRef<Set<number> | null>(null)
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (active.length === 0) return
    const timer = setInterval(() => setNow(Date.now()), 1000)     // 지난 시간을 1초마다 다시 센다
    return () => clearInterval(timer)
  }, [active.length])

  useEffect(() => {
    if (!data) return
    const before = seen.current
    seen.current = new Set(data.filter(busy).map((r) => r.run_id))
    if (!before) return
    for (const r of data) {
      if (!before.has(r.run_id) || busy(r) || cancelled(r)) continue
      const link = { href: href(`/reviews/${r.run_id}`), label: r.stage === 'FAILED' ? '실패 보기' : '판정 확인' }
      if (r.stage === 'FAILED') toast.show(`${r.review_no} ${nameOf(r)} 분석이 멈췄습니다`, 'error', link)
      else toast.show(`${r.review_no} ${nameOf(r)} 분석이 끝났습니다`, 'success', link)
    }
  }, [data, toast])

  useEffect(() => { if (open && active.length === 0) onClose() }, [open, active.length, onClose])
  if (active.length === 0) return null

  const pct = Math.round(active.reduce((s, r) => s + progress(r), 0) / active.length)
  const stalled = (r: RunListItem) => now - Date.parse(r.step_updated_at) > STALL_MS
  const warn = active.some(stalled)
  const title = `분석 진행 ${active.length}건 · 평균 ${pct} %${warn ? ' · 진행 없음 있음' : ''}`
  return (
    <div className="ntw">
      <button type="button" className={'anb' + (warn ? ' warn' : '')} aria-expanded={open} onClick={onToggle} title={title}>
        <span className="anr" aria-hidden="true" style={{ '--p': `${pct}%` } as React.CSSProperties} />
        <span>분석 {active.length}건 · <b>{pct} %</b></span>
      </button>
      {open && (
        <div className="anp" role="dialog" aria-label="분석 진행">
          <h4>분석 중 {active.length}건</h4>
          {active.map((r) => {
            const p = progress(r)
            const w = stalled(r)
            return (
              <div key={r.run_id} className={'ani' + (w ? ' warn' : '')}>
                <div className="t"><b>{r.review_no}</b><span>{nameOf(r)}</span></div>
                <div className="s"><span>{stepText(r)}</span><b>{p} %</b></div>
                <div className="anbar" role="progressbar" aria-label={`${r.review_no} 진행`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={p}>
                  <i style={{ width: `${p}%` }} />
                </div>
                <div className="s"><span>지난 시간 {duration(now - Date.parse(r.started_at))}</span></div>
                {w && <div className="w">{Math.floor((now - Date.parse(r.step_updated_at)) / 60000)}분째 진행이 없습니다. 처리 상태 화면에서 확인해 주세요.</div>}
                <div className="a"><a href={href(`/reviews/${r.run_id}`)} onClick={onClose}>진행 보기</a></div>
              </div>
            )
          })}
          <div className="anf">다른 화면으로 가도 분석은 계속됩니다. 끝나면 화면 오른쪽 위에 알려 드립니다.</div>
        </div>
      )}
    </div>
  )
}
