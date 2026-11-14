import { useState } from 'react'
import { api, type RunSummary } from '../../api'
import { stamp } from '../../components/format'
import { historyText, reasonLabel } from '../../components/history'
import { PIPELINE_STEPS, STEP_NAMES } from '../../components/labels'
import { useLoad } from '../../components/useLoad'
import { usePage } from '../../components/usePage'
import { useSession } from '../../shell/useSession'

// SCR-08-9 이력 탭 (목업 v4.57 Detail #log). docs/screens/SCR-08-9-이력.md
// 사람이 바꾼 기록(review_log)을 새것부터, 맨 아래에 시스템이 판정을 만든 줄.

const SKIP_REASONS = new Set(['검토 정보 고치기', '손실값 고치기', '비교 제품 바꿔 보기', '상신 취소', '반려 뒤 다시 확인'])

/** 단계부터 다시 처리 (add-step-rewind, C2): 담당자 확인 단계의 엔지니어만. 사람 확정은 이어받는다 */
function Rewind({ run, onChanged }: { run: RunSummary; onChanged: () => void }) {
  const { user } = useSession()
  const [step, setStep] = useState('judge')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  if (run.stage !== 'ENGINEER_REVIEW' || user?.role !== 'ENGINEER') return null
  const go = () => {
    setBusy(true)
    setError(null)
    api.rewind(run.run_id, step, reason.trim(), user.user_id).then(onChanged)
      .catch((e: Error) => setError(e.message)).finally(() => setBusy(false))
  }
  return (
    <div className="rwbox" role="group" aria-label="되돌려 다시 처리">
      <label htmlFor="rwstep">단계부터 다시 처리</label>
      <select className="fi" id="rwstep" value={step} onChange={(e) => setStep(e.target.value)}>
        {PIPELINE_STEPS.map((s) => <option key={s} value={s}>{STEP_NAMES[s] ?? s}</option>)}
      </select>
      <input className="fi" aria-label="다시 처리하는 사유" placeholder="사유 (예: 판정 규칙을 고쳐서)" value={reason} onChange={(e) => setReason(e.target.value)} />
      <button type="button" className="bo" disabled={busy || !reason.trim()} onClick={go}>다시 처리</button>
      <p className="en">고른 단계부터 다시 돌고 담당자 확인에서 다시 멈춥니다. 사람이 확정·수정한 판정은 같은 줄이면 그대로 이어받습니다.</p>
      {error && <p className="c-red" role="alert">{error}</p>}
    </div>
  )
}

export function LogTab({ run, tick, onChanged }: { run: RunSummary; tick: number; onChanged: () => void }) {
  const log = useLoad(() => api.history(run.run_id), [run.run_id, tick])
  // "시스템 · 판정 n줄 생성" 줄(null)도 한 줄로 세어 맨 끝에 둔다 (update-detail-tab-paging)
  const rows = [...[...(log.data ?? [])].reverse(), ...(run.finished_at ? [null] : [])]
  const { shown, pager } = usePage(rows)
  return (
    <section className="sec" id="log">
      <div className="sech"><h2>이력</h2></div>
      <Rewind run={run} onChanged={onChanged} />
      {log.error && <p role="alert">{log.error} <button type="button" className="lnk" onClick={log.reload}>다시 불러오기</button></p>}
      <table className="mini"><tbody>
        {shown.map((l) => l ? (
          <tr key={l.log_id}>
            <td style={{ width: 92, whiteSpace: 'nowrap', color: 'var(--c-muted)' }}>{stamp(l.acted_at)}</td>
            <td style={{ width: 96, whiteSpace: 'nowrap' }}>{l.actor}</td>
            <td>{historyText(l)}{l.reason && !SKIP_REASONS.has(l.reason) && <div className="en">{reasonLabel(l)}: {l.reason}</div>}</td>
          </tr>
        ) : (
          <tr key="system">
            <td style={{ width: 92, whiteSpace: 'nowrap', color: 'var(--c-muted)' }}>{stamp(run.finished_at!)}</td>
            <td style={{ width: 96, whiteSpace: 'nowrap' }}>시스템</td>
            <td>판정 {run.judgments}건 생성</td>
          </tr>
        ))}
      </tbody></table>
      {pager}
    </section>
  )
}
