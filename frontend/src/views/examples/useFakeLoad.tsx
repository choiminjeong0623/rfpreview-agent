import { useEffect, useRef, useState } from 'react'

// 예시 화면의 내보내기 (목업 runLd: 로딩 화면 → 알림). 파일은 만들지 않고, 저장도 하지 않는다 (예시 화면 규칙).

type Job = { label: string; stages: [number, string][]; pct: number; done: string; after?: () => void }

export function useFakeLoad() {
  const [job, setJob] = useState<Job | null>(null)
  const [toast, setToast] = useState('')
  const timer = useRef<number | undefined>(undefined)
  useEffect(() => () => { clearInterval(timer.current) }, [])

  /** done이 비어 있으면 알림 없이 끝낸다. after는 로딩 화면을 닫은 뒤 부른다 (목업 runLd의 after) */
  const start = (label: string, stages: [number, string][], done: string, after?: () => void) => {
    clearInterval(timer.current)
    setJob({ label, stages, pct: 0, done, after })
    timer.current = window.setInterval(() => setJob((j) => j && { ...j, pct: Math.min(100, j.pct + 8) }), 90)
  }
  const finished = job?.pct === 100 ? job : null
  useEffect(() => {
    if (finished === null) return
    clearInterval(timer.current)
    const t = setTimeout(() => { setJob(null); setToast(finished.done); finished.after?.() }, 350)
    return () => clearTimeout(t)
  }, [finished])
  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(''), 3000)
    return () => clearTimeout(t)
  }, [toast])

  const text = job ? [...job.stages].reverse().find(([at]) => job.pct >= at)?.[1] : ''
  const view = (
    <>
      {job && (
        <div className="ldo"><div className="ldc">
          <img src="/img/spec2win-color.png" alt="Spec2Win" width={200} height={40} />
          <div className="ldrow">
            <div className="ldbar" role="progressbar" aria-label={job.label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={job.pct}>
              <div className="ldfill" style={{ width: `${job.pct}%` }} /></div>
            <span className="ldpct">{job.pct}%</span>
          </div>
          <div className="ldtx" aria-live="polite">{text}</div>
        </div></div>
      )}
      {toast && <div className="ltoast" role="status"><span className="ms" aria-hidden="true">check_circle</span>{toast}</div>}
    </>
  )
  return { start, view }
}
