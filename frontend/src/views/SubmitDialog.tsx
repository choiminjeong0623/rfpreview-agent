import { useEffect, useState } from 'react'
import { api, type RunSummary } from '../api'
import { reviewTitle } from '../components/format'
import { useLoad } from '../components/useLoad'
import { useSession } from '../shell/useSession'
import { loadCounts, overRatio, ratioText } from '../components/approval'
import { CheckList } from './CheckList'

// SCR-08-10 결재 상신 창 (목업 v4.57 Detail의 결재 상신). docs/screens/SCR-08-10-결재상신.md
// 참조·첨부는 update-approval-flow 범위 밖이라 없다 (SCR-08-10_공유.md).

export function SubmitDialog({ run, onClose, onDone }: { run: RunSummary; onClose: () => void; onDone: () => void }) {
  const { user, users } = useSession()
  const screen = useLoad(() => api.approval(run.run_id), [run.run_id])
  const counts = useLoad(() => loadCounts(run.run_id), [run.run_id])
  const approvers = users.filter((u) => u.role === 'APPROVER')
  const [picked, setPicked] = useState<number | null>(null)
  const [comment, setComment] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  // 결재자: 직접 고른 사람 → 직전 상신의 결재자 → 승인자가 1명이면 그 사람
  const previous = screen.data?.approval?.approver_id ?? null
  const approverId = picked ?? (approvers.some((u) => u.user_id === previous) ? previous : approvers.length === 1 ? approvers[0].user_id : null)
  const approver = approvers.find((u) => u.user_id === approverId)
  const found = screen.data?.preview ?? []
  const ratio = screen.data?.review_ratio
  const unread = screen.data?.read_unchecked
  const nWarn = ratio ? found.length + (unread ? 1 : 0) : 0
  const ready = approverId !== null && comment.trim() !== '' && user?.role === 'ENGINEER'
  const c = counts.data
  const sum: [string, string, string][] = c && ratio ? [
    ['일탈 후보', String(c.deviations), c.deviations ? 'c-red' : ''],
    ['질의 후보', String(c.queries), c.queries ? 'c-ora' : ''],
    ['확인 필요 비율', ratioText(ratio), overRatio(ratio) ? 'c-ora' : 'c-green'],
    ['보증값 작성', String(c.toFill), c.toFill ? 'c-blue' : ''],
    ['손실 환산 가산액 (참고)', c.loss, ''],
  ] : []

  const submit = () => {
    if (!ready || approverId === null) return
    setBusy(true)
    setError(null)
    api.submit(run.run_id, approverId, comment.trim(), user!.user_id).then(onDone, (e: Error) => setError(e.message))
      .finally(() => setBusy(false))
  }

  return (
    <div className="mdo" onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="apw" role="dialog" aria-modal="true" aria-labelledby="apTitle">
        <div className="mdh">
          <div style={{ flex: '1 1 auto', minWidth: 0 }}>
            <div className="apid">{run.review_no} · {reviewTitle(run)}</div>
            <h2 id="apTitle" style={{ margin: '2px 0 0', fontSize: 'var(--fs-h3)' }}>결재 상신</h2>
          </div>
          <button type="button" className="ib" onClick={onClose} aria-label="닫기" title="닫기 (Esc)"><span className="ms" aria-hidden="true">close</span></button>
        </div>
        <div className="apb">
          <section className="aps"><h3>결재선</h3>
            <div className="apline">
              <div className="apnode"><span className="aprole">기안</span><b>{user?.user_name ?? '—'}</b><span className="apsub">기술 검토</span></div>
              <span className="ms aparr" aria-hidden="true">arrow_forward</span>
              <div className="apnode on"><span className="aprole">결재</span>
                <select className="fi" aria-label="결재자" value={approverId ?? ''} onChange={(e) => setPicked(e.target.value ? Number(e.target.value) : null)}>
                  {approverId === null && <option value="">결재자 고르기</option>}
                  {approvers.map((u) => <option key={u.user_id} value={u.user_id}>{u.user_name}</option>)}
                </select>
                <span className="apsub">승인자</span>
              </div>
            </div>
          </section>

          <section className="aps"><h3>검토 요약</h3>
            <div className="apsum">
              {sum.map(([k, v, cls]) => <div key={k}><span>{k}</span><b className={cls}>{v}</b></div>)}
            </div>
          </section>

          <section className="aps"><h3>상신 전 확인<span className="apn">
            {ratio && (nWarn ? `확인할 항목 ${nWarn}건 · 남아 있어도 상신할 수 있습니다` : '모두 확인했습니다')}</span></h3>
            {ratio && <CheckList found={found} ratio={ratio} unread={unread} />}
          </section>

          <section className="aps"><h3>상신 의견<span className="auto2">필수</span></h3>
            <textarea className="fi" rows={3} aria-label="상신 의견" value={comment} onChange={(e) => setComment(e.target.value)}
              placeholder={nWarn ? '예: 일탈 2건은 옵션 제안으로 대응, 질의 1건은 10-27 회신 예정' : '결재자에게 전할 내용'} />
            {user && user.role !== 'ENGINEER' && <p className="aphint">결재 상신은 기술 검토 엔지니어만 할 수 있습니다. 머리글에서 사용자를 바꿔 주세요.</p>}
            {error && <p className="aphint" role="alert">{error}</p>}
          </section>
        </div>
        <div className="mdf">
          <span className="mdf-n" style={{ marginRight: 'auto' }}>결재자 {approver?.user_name ?? '고르지 않음'}</span>
          <button type="button" className="bo" onClick={onClose}>취소</button>
          <button type="button" className="bp" disabled={!ready || busy} onClick={submit}>
            <span className="ms" aria-hidden="true" style={{ fontSize: 'var(--ic-s)' }}>send</span>{busy ? '상신하는 중…' : '결재 상신'}</button>
        </div>
      </div>
    </div>
  )
}
