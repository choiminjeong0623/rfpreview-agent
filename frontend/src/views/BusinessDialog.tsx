import { useEffect, useState } from 'react'
import { api, type BusinessDetail, type BusinessInfo } from '../api'
import { useSession } from '../shell/useSession'
import './detail.css'

// 사업 상세의 "사업 정보 고치기" 창 (SCR-05, add-project-status). 모양은 검토 정보 고치기 창과 같다.

type Key = 'business_name' | 'customer_name' | 'country' | 'tender_no' | 'order_mode' | 'due_date' | 'sales_id'
type Form = Record<Key, string>

const LABELS: [Key, string, number][] = [
  ['business_name', '사업명', 200], ['customer_name', '고객사', 200], ['country', '국가', 60],
  ['tender_no', '고객 입찰 번호', 80], ['order_mode', '발주 방식', 200],
]

export function BusinessDialog({ business: b, onClose, onSaved }: { business: BusinessDetail; onClose: () => void; onSaved: () => void }) {
  const { user, users } = useSession()
  const start: Form = {
    business_name: b.business_name, customer_name: b.customer_name ?? '', country: b.country ?? '', tender_no: b.tender_no ?? '',
    order_mode: b.order_mode ?? '', due_date: b.business_due_date ?? '', sales_id: b.sales_id ? String(b.sales_id) : '',
  }
  const [form, setForm] = useState<Form>(start)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  const changed = (Object.keys(form) as Key[]).filter((k) => form[k] !== start[k])
  const save = () => {
    setBusy(true)
    setError(null)
    const body: BusinessInfo = Object.fromEntries(changed.map((k) => [k, k === 'sales_id' ? (form[k] ? Number(form[k]) : null) : form[k]]))
    api.updateBusiness(b.business_id, body, user?.user_id ?? null).then(onSaved, (e: Error) => setError(e.message))
      .finally(() => setBusy(false))
  }
  const set = (k: Key) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value })
  return (
    <div className="mdo" onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="apw" role="dialog" aria-modal="true" aria-labelledby="bizTitle">
        <div className="mdh">
          <div style={{ flex: '1 1 auto', minWidth: 0 }}>
            <div className="apid">{b.business_no} · {b.business_name}</div>
            <h2 id="bizTitle" style={{ margin: '2px 0 0', fontSize: 'var(--fs-h3)' }}>사업 정보 고치기</h2>
          </div>
          <button type="button" className="ib" onClick={onClose} aria-label="닫기" title="닫기 (Esc)"><span className="ms" aria-hidden="true">close</span></button>
        </div>
        <div className="apb">
          <section className="aps">
            <div className="infog">
              {LABELS.map(([k, label, max]) => (
                <label key={k}>{label}<input className="fi" value={form[k]} maxLength={max} onChange={set(k)} /></label>
              ))}
              <label>제출 마감일<input className="fi" type="date" value={form.due_date} onChange={set('due_date')} /></label>
              <label>영업 담당
                <select className="fi" value={form.sales_id} onChange={set('sales_id')}>
                  <option value="">없음</option>
                  {users.filter((u) => u.role === 'SALES').map((u) => <option key={u.user_id} value={u.user_id}>{u.user_name}</option>)}
                </select>
              </label>
            </div>
            <p className="aphint" style={{ color: 'var(--c-muted)' }}>고친 칸은 사업 이력에 남습니다. 사업명을 고치면 연결된 검토의 사업명도 바뀝니다. 사업 정보는 판정에 쓰지 않습니다.</p>
          </section>
        </div>
        <div className="mdf">
          <span className="mdf-n" style={{ marginRight: 'auto', color: error ? 'var(--c-red)' : undefined }} role={error ? 'alert' : undefined}>
            {error ?? (changed.length ? `${changed.length}칸 바뀜` : '바뀐 칸 없음')}</span>
          <button type="button" className="bo" onClick={onClose}>취소</button>
          <button type="button" className="bp" disabled={busy || changed.length === 0 || !form.business_name.trim()} onClick={save}>저장</button>
        </div>
      </div>
    </div>
  )
}
