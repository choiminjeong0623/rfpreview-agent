import { useCallback, useMemo, useRef, useState } from 'react'
import { ToastCtx, TOAST_MS, type ToastKind, type ToastLink } from './toastContext'

// 알림 쌓기 (SCR-00 7장, 목업 v4.96). 오른쪽 위에 위에서 아래로 쌓는다.
// 성공·안내는 4초 뒤 사라지고, 오류는 닫기 전까지 남는다. 같은 문장이 떠 있으면 하나만.
// 동작 결과(done)는 아래 가운데에 하나만 보이고 새 결과가 오면 바꿔 끼운다 (update-action-toast-place).
type Toast = { id: number; kind: ToastKind; text: string; link?: ToastLink }

const ICON: Record<ToastKind, string> = { success: 'check_circle', info: 'info', error: 'error' }

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [list, setList] = useState<Toast[]>([])
  const seq = useRef(0)
  const remove = useCallback((id: number) => setList((l) => l.filter((t) => t.id !== id)), [])
  const show = useCallback((text: string, kind: ToastKind = 'success', link?: ToastLink) => {
    // 갱신 함수 안에서는 타이머를 걸지 않는다 (StrictMode에서 두 번 불릴 수 있음)
    const id = ++seq.current
    setList((l) => l.some((t) => t.text === text && t.kind === kind) ? l : [...l, { id, kind, text, link }])
    if (kind !== 'error') setTimeout(() => remove(id), TOAST_MS)
  }, [remove])
  const [snack, setSnack] = useState<{ id: number; text: string; link?: ToastLink } | null>(null)
  const done = useCallback((text: string, link?: ToastLink) => {
    const id = ++seq.current
    setSnack({ id, text, link })
    setTimeout(() => setSnack((s) => (s?.id === id ? null : s)), TOAST_MS)
  }, [])
  const api = useMemo(() => ({ show, done }), [show, done])
  return (
    <ToastCtx.Provider value={api}>
      {children}
      {list.length > 0 && (
        <div className="uitw" aria-live="polite">
          {list.map((t) => (
            <div key={t.id} className={`uit ${t.kind === 'success' ? '' : t.kind}`} role={t.kind === 'error' ? 'alert' : 'status'}>
              <span className="ms" aria-hidden="true">{ICON[t.kind]}</span>
              <p>{t.text}{t.link && <> <a href={t.link.href} onClick={() => remove(t.id)}>{t.link.label}</a></>}</p>
              <button type="button" onClick={() => remove(t.id)}>닫기</button>
            </div>
          ))}
        </div>
      )}
      {snack && (
        <div key={snack.id} className="uisnk" role="status" aria-live="polite">
          <span className="ms" aria-hidden="true">check_circle</span>
          <p>{snack.text}{snack.link && <> <a href={snack.link.href} onClick={() => setSnack(null)}>{snack.link.label}</a></>}</p>
        </div>
      )}
    </ToastCtx.Provider>
  )
}
