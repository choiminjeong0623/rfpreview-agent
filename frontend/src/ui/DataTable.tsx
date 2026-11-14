import { Pager } from '../components/Pager'

// 목록 표 (목업 .tw > table.tbl + .pager). 맨 왼쪽 순번은 쪽을 넘겨도 이어진다 (SCR-00 6장).
// rows가 null이면 로딩, error가 있으면 오류, 빈 배열이면 empty 문장. 쪽 나누기는 total을 주면 Pager를 붙인다.
export type Column<T> = {
  key: string
  head: React.ReactNode
  cell: (row: T) => React.ReactNode
  num?: boolean
  width?: number
}

export function DataTable<T>({ columns, rows, rowKey, error, onRetry, empty, page = 1, size = 10, total, onPage, onSize, onRow, selected, label }: {
  columns: Column<T>[]
  rows: T[] | null
  rowKey: (row: T) => string | number
  error?: string | null
  onRetry?: () => void
  empty: string
  page?: number
  size?: number
  /** 전체 줄 수. 주면 표 아래 페이지 번호 */
  total?: number
  onPage?: (page: number) => void
  onSize?: (size: number) => void
  onRow?: (row: T) => void
  selected?: string | number | null
  label?: string
}) {
  const span = columns.length + 1
  const start = (page - 1) * size
  let body: React.ReactNode
  if (error) body = <tr><td colSpan={span} className="uis err" role="alert">{error}{onRetry && <> <button type="button" className="bo" onClick={onRetry}>다시 불러오기</button></>}</td></tr>
  else if (rows === null) body = <tr><td colSpan={span} className="uis" role="status">불러오는 중</td></tr>
  else if (rows.length === 0) body = <tr><td colSpan={span} className="uis">{empty}</td></tr>
  else body = rows.map((r, i) => {
    const k = rowKey(r)
    return (
      <tr key={k} className={selected === k ? 'on' : undefined} onClick={onRow ? () => onRow(r) : undefined}
        style={onRow ? { cursor: 'pointer' } : undefined}>
        <td className="sq">{start + i + 1}</td>
        {columns.map((c) => <td key={c.key} className={c.num ? 'num' : undefined}>{c.cell(r)}</td>)}
      </tr>
    )
  })
  return (
    <>
      <div className="tw">
        <table className="tbl" aria-label={label}>
          <thead><tr>
            <th className="sq" scope="col">순번</th>
            {columns.map((c) => <th key={c.key} scope="col" className={c.num ? 'num' : undefined} style={c.width ? { width: c.width } : undefined}>{c.head}</th>)}
          </tr></thead>
          <tbody>{body}</tbody>
        </table>
      </div>
      {total !== undefined && onPage && onSize && rows && rows.length > 0 &&
        <Pager total={total} page={page} size={size} shown={rows.length} onPage={onPage} onSize={onSize} />}
    </>
  )
}
