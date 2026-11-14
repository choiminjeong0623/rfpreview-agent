import { useEffect, useRef } from 'react'

// 창 (목업 .mdo > .apw 모양). Esc · 바깥 누르기 · 닫기 단추로 닫는다.
// 열리면 첫 입력 칸(없으면 창)에 초점, 닫히면 창을 연 단추로 초점이 돌아간다.
export function Modal({ title, onClose, children, footer, width }: {
  title: string; onClose: () => void; children: React.ReactNode; footer?: React.ReactNode; width?: number
}) {
  const box = useRef<HTMLDivElement>(null)
  const close = useRef(onClose)
  useEffect(() => { close.current = onClose })
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null
    const first = box.current?.querySelector<HTMLElement>('input,select,textarea')
    ;(first ?? box.current)?.focus()
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') { e.stopPropagation(); close.current() } }
    window.addEventListener('keydown', onKey)
    return () => { window.removeEventListener('keydown', onKey); opener?.focus?.() }
  }, [])
  return (
    <div className="uim" onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div ref={box} className="uid" role="dialog" aria-modal="true" aria-label={title} tabIndex={-1}
        style={width ? ({ '--uid-w': `${width}px` } as React.CSSProperties) : undefined}>
        <div className="uid-h">
          <h2>{title}</h2>
          <button type="button" className="tl" aria-label="닫기" title="닫기" onClick={onClose}>
            <span className="ms" aria-hidden="true">close</span>
          </button>
        </div>
        <div className="uid-b">{children}</div>
        {footer && <div className="uid-f">{footer}</div>}
      </div>
    </div>
  )
}
