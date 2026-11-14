import { useEffect, useState } from 'react'
import { api, type ReviewInfo, type RunSummary } from '../api'
import { reviewTitle } from '../components/format'
import { useSession } from '../shell/useSession'
import './detail.css'

// 검토 머리글의 "검토 정보 고치기" 창 (SCR-08). 모양은 목업 결재 상신 창(.mdo > .apw)을 따른다.

type Form = Record<Exclude<keyof ReviewInfo, 'engineer_id'>, string> & { engineer_id: string }

const LABELS: [keyof Form, string, number][] = [
  ['project_name', '사업명', 200], ['review_name', '설비 범위', 200], ['customer_name', '고객사', 200], ['country', '국가', 60],
]

export function ReviewInfoDialog({ run, onClose, onSaved }: { run: RunSummary; onClose: () => void; onSaved: () => void }) {
  const { user, users } = useSession()
  const start: Form = {
    project_name: run.project_name ?? '', review_name: run.review_name ?? '', customer_name: run.customer_name ?? '',
    country: run.country ?? '', due_date: run.due_date ?? '', engineer_id: run.engineer_id ? String(run.engineer_id) : '',
  }
  const [form, setForm] = useState<Form>(start)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  const changed = (Object.keys(form) as (keyof Form)[]).filter((k) => form[k] !== start[k])
  const save = () => {
    setBusy(true)
    setError(null)
    const body = Object.fromEntries(changed.map((k) => [k, k === 'engineer_id' ? (form[k] ? Number(form[k]) : null) : form[k]]))
    api.updateInfo(run.run_id, body, user?.user_id ?? null).then(onSaved, (e: Error) => setError(e.message))
      .finally(() => setBusy(false))
  }
  const set = (k: keyof Form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value })
  return (
    <div className="mdo" onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="apw" role="dialog" aria-modal="true" aria-labelledby="infoTitle">
        <div className="mdh">
          <div style={{ flex: '1 1 auto', minWidth: 0 }}>
            <div className="apid">{run.review_no} · {reviewTitle(run)}</div>
            <h2 id="infoTitle" style={{ margin: '2px 0 0', fontSize: 'var(--fs-h3)' }}>검토 정보 수정</h2>
          </div>
          <button type="button" className="ib" onClick={onClose} aria-label="닫기" title="닫기 (Esc)"><span className="ms" aria-hidden="true">close</span></button>
        </div>
        <div className="apb">
          <section className="aps">
            <div className="infog">
              {LABELS.map(([k, label, max]) => (
                <label key={k}>{label}<input className="fi" value={form[k]} maxLength={max} onChange={set(k)}
                  disabled={k === 'project_name' && run.business_id !== null}
                  title={k === 'project_name' && run.business_id !== null ? '사업에 연결된 검토의 사업명은 사업 상세에서 고칩니다' : undefined} /></label>
              ))}
              <label>제출 마감일<input className="fi" type="date" value={form.due_date} onChange={set('due_date')} /></label>
              <label>담당 엔지니어
                <select className="fi" value={form.engineer_id} onChange={set('engineer_id')}>
                  <option value="">없음</option>
                  {users.filter((u) => u.role === 'ENGINEER').map((u) => <option key={u.user_id} value={u.user_id}>{u.user_name}</option>)}
                </select>
              </label>
            </div>
            <p className="aphint" style={{ color: 'var(--c-muted)' }}>고친 칸은 이력 탭에 남습니다. 검토 정보는 판정에 쓰지 않습니다.
              {run.business_no && <> 사업명은 <a className="lnk" href={`#/projects/${run.business_no}`}>사업 상세</a>에서 고칩니다.</>}</p>
          </section>
        </div>
        <div className="mdf">
          <span className="mdf-n" style={{ marginRight: 'auto', color: error ? 'var(--c-red)' : undefined }} role={error ? 'alert' : undefined}>
            {error ?? (changed.length ? `${changed.length}칸 바뀜` : '바뀐 칸 없음')}</span>
          <button type="button" className="bo" onClick={onClose}>취소</button>
          <button type="button" className="bp" disabled={busy || changed.length === 0} onClick={save}>저장</button>
        </div>
      </div>
    </div>
  )
}
