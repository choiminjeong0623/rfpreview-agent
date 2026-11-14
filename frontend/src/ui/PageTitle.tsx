// 화면 제목 줄 (목업 .ttl > h1 + 오른쪽 단추). 제목은 화면마다 하나.
export function PageTitle({ title, sub, children }: { title: React.ReactNode; sub?: React.ReactNode; children?: React.ReactNode }) {
  return (
    <div className="ttl">
      <h1>{title}{sub && <span style={{ marginLeft: 'var(--s-2)', fontSize: 'var(--t-sm)', fontWeight: 400, color: 'var(--c-muted)' }}>{sub}</span>}</h1>
      {children && <div style={{ display: 'flex', gap: 'var(--s-2)', alignItems: 'center' }}>{children}</div>}
    </div>
  )
}
