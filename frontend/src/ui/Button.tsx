import { useId } from 'react'

// 단추 (목업 .bp 주 · .bo 보조). 권한·단계 때문에 못 누르면 숨기지 않고 잠근 채 이유를 붙인다 (_공통규칙.md 1장).
type Props = Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, 'className'> & {
  kind?: 'primary' | 'secondary'
  icon?: string
  /** 잠근 이유. 주면 단추가 잠기고, 마우스를 올리거나 화면 읽기 도구로 이유가 보인다 */
  disabledReason?: string | null
  busy?: boolean
}

export function Button({ kind = 'secondary', icon, disabledReason, busy, disabled, children, type = 'button', ...rest }: Props) {
  const id = useId()
  const locked = Boolean(disabledReason)
  return (
    <>
      <button {...rest} type={type} className={kind === 'primary' ? 'bp' : 'bo'} disabled={disabled || locked || busy}
        title={disabledReason ?? rest.title} aria-describedby={locked ? id : undefined} aria-busy={busy || undefined}>
        {icon && <span className="ms" aria-hidden="true" style={{ fontSize: 'var(--ic-s)' }}>{icon}</span>}
        {children}
      </button>
      {locked && <span id={id} className="sr">{disabledReason}</span>}
    </>
  )
}
