import { useState } from 'react'
import { api, type OutputItem } from '../../api'
import { STATUS_NAMES } from '../../components/labels'
import { useSession } from '../../shell/useSession'

// SCR-08-11 일탈 목록·질의 문장 고치기 (목업 v4.57 Detail 패널·판정 상세 창의 문장 칸 #draft).
// 고치기·빼기는 사유가 필요하다 (POST /actions output_item EDIT·REJECT). 확정은 사유 없이.

const TONES: Record<string, string> = { CANDIDATE: 'c-grey', CONFIRMED: 'c-green', EDITED: 'c-green', REMOVED: 'c-grey' }

// 저장·빼기·확정이 끝나면 부모 화면이 알림을 띄운다. 이 칸은 다시 그려지면서 사라지기 때문이다.
const DONE_MESSAGES = {
  EDIT: '정상적으로 사유가 등록되었습니다. 고친 문장을 저장했습니다.',
  REJECT: '정상적으로 사유가 등록되었습니다. 목록에서 뺐습니다.',
  CONFIRM: '문장을 확정했습니다.',
}

export function OutputEditor({ runId, item, id, canEdit, onDone, onSaved }: {
  runId: number; item: OutputItem; id: string; canEdit: boolean; onDone: () => void; onSaved?: (message: string) => void
}) {
  const { user } = useSession()
  const [text, setText] = useState(item.text_draft)
  const [dropping, setDropping] = useState(false)
  const [why, setWhy] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const changed = text.trim() !== item.text_draft.trim()
  const removed = item.status === 'REMOVED'
  const act = (action: 'EDIT' | 'CONFIRM' | 'REJECT') => {
    setBusy(true)
    setError(null)
    api.act(runId, {
      target: 'output_item', target_id: item.item_id, action, actor_id: user!.user_id,
      value: action === 'EDIT' ? { text: text.trim() } : undefined, reason: action === 'CONFIRM' ? undefined : why.trim(),
    }).then(() => { setWhy(''); setDropping(false); onSaved?.(DONE_MESSAGES[action]); onDone() }, (e: Error) => setError(e.message)).finally(() => setBusy(false))
  }
  return (
    <div>
      <label className="lbl" htmlFor={id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
        <span>{item.list_kind === 'QUERY' ? '질의 문장' : '일탈 목록 문장'} <span className={`st ${TONES[item.status] ?? 'c-grey'}`} style={{ marginLeft: 4 }}>{STATUS_NAMES[item.status] ?? item.status}</span></span>
        {item.drafted_by === 'AI' && <span className="ai"><span className="ms" aria-hidden="true">auto_awesome</span>AI 초안</span>}</label>
      <textarea className="ta" id={id} value={text} readOnly={!canEdit || removed} onChange={(e) => setText(e.target.value)} />
      {item.number_check === 'MISMATCH' && <p className="aphint">숫자 확인 필요: {item.number_detail}</p>}
      {item.is_assumed && <span className="st c-ora">팀 가정</span>}
      {canEdit && !removed && (changed || dropping
        ? <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginTop: 6 }}>
            <input className="fi" aria-label={changed ? '고친 사유' : '빼는 사유'} placeholder={changed ? '고친 사유 (이력에 남음)' : '빼는 사유'} value={why}
              onChange={(e) => setWhy(e.target.value)} style={{ flex: 1, height: 32 }} />
            <button type="button" className="bp" disabled={busy || !why.trim() || (changed && !text.trim())} onClick={() => act(changed ? 'EDIT' : 'REJECT')}>
              {changed ? '문장 저장' : '제외'}</button>
            <button type="button" className="bo" onClick={() => { setText(item.text_draft); setDropping(false); setWhy('') }}>취소</button>
          </div>
        : <div style={{ display: 'flex', gap: 12, marginTop: 4 }}>
            <button type="button" className="lnk" disabled={busy || item.status === 'CONFIRMED'} onClick={() => act('CONFIRM')}>문장 확정</button>
            <button type="button" className="lnk" disabled={busy} onClick={() => setDropping(true)}>목록에서 제외</button>
          </div>)}
      {error && <p className="aphint" role="alert">{error}</p>}
    </div>
  )
}
