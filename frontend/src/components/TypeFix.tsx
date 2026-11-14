import { useState } from 'react'
import { api } from '../api'
import { useSession } from '../shell/useSession'
import { TYPE_NAMES } from './labels'

// 사람이 요구사항 주 유형 고치기 (add-type-examples, C3). 엔지니어·승인자만.
// 고친 유형은 다른 문서를 분석할 때 AI 유형 질문에 "사람이 고른 예"로 들어간다.

const CHOICES: [string, string][] = [...Object.entries(TYPE_NAMES), ['NONE', '미분류']]

export function TypeFix({ runId, requirementId, current }: { runId: number; requirementId: number; current: string | null }) {
  const { user } = useSession()
  const [open, setOpen] = useState(false)
  const [code, setCode] = useState(current ?? 'NONE')
  const [reason, setReason] = useState('')
  const [shown, setShown] = useState(current ?? 'NONE')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  if (!user || (user.role !== 'ENGINEER' && user.role !== 'APPROVER')) return null
  const name = (c: string) => (c === 'NONE' ? '미분류' : TYPE_NAMES[c] ?? c)
  const save = () => {
    setBusy(true)
    setMsg(null)
    api.setType(runId, requirementId, code, reason.trim() || null, user.user_id)
      .then(() => {
        setShown(code)
        setOpen(false)
        setMsg({ ok: true, text: `유형을 ${name(code)}(으)로 고쳤습니다. 담당 전달을 다시 만들고, 다른 문서 분석에서 AI 예시로 씁니다.` })
      }, (e: Error) => setMsg({ ok: false, text: e.message }))
      .finally(() => setBusy(false))
  }
  return (
    <div className="tfix" data-testid="type-fix" style={{ margin: '8px 0' }}>
      {!open && <button type="button" className="uib" onClick={() => setOpen(true)}>
        <span className="ms" aria-hidden="true">edit</span>유형 수정<span className="uib-v">· 지금 {name(shown)}</span></button>}
      {open && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
          <select className="fi" aria-label="유형" value={code} onChange={(e) => setCode(e.target.value)} style={{ maxWidth: 160 }}>
            {CHOICES.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <input className="fi" aria-label="고친 사유" placeholder="사유 (선택)" value={reason} maxLength={200}
            onChange={(e) => setReason(e.target.value)} style={{ flex: 1, minWidth: 140 }} />
          <button type="button" className="bp" disabled={busy || code === shown} onClick={save}>{busy ? '저장 중…' : '유형 저장'}</button>
          <button type="button" className="bo" onClick={() => setOpen(false)}>취소</button>
        </div>
      )}
      {msg && <p className={msg.ok ? 'dimv' : 'c-red'} role={msg.ok ? 'status' : 'alert'}>{msg.text}</p>}
    </div>
  )
}
