// 표 아래 페이지 번호 (목업 .pager). 쪽 크기는 기본 10·20·50 (sizes로 바꿈, 협조 요청은 5·10·20).
// 페이지가 많으면 처음·끝과 지금 페이지 앞뒤 2쪽만 보이고 사이는 "…"로 줄인다 (pageItems).
import { pageItems } from './pageItems'

export function Pager({ total, page, size, shown, onPage, onSize, sizes = [10, 20, 50] }: {
  total: number; page: number; size: number; shown: number
  onPage: (page: number) => void; onSize: (size: number) => void; sizes?: number[]
}) {
  const pages = Math.max(1, Math.ceil(total / size))
  const from = (page - 1) * size + 1
  return (
    <div className="pager">
      <span>{total ? `${from}–${from + shown - 1}` : '0'} / 전체 {total}건</span>
      <span className="pg" role="navigation" aria-label="페이지">
        <button type="button" onClick={() => onPage(Math.max(1, page - 1))} disabled={page <= 1} aria-label="이전 페이지">
          <span className="ms" aria-hidden="true" style={{ fontSize: 'var(--ic-s)' }}>chevron_left</span>
        </button>
        {pageItems(page, pages).map((n, i) => n === null
          ? <span key={`gap${i}`} aria-hidden="true" style={{ minWidth: 20, textAlign: 'center', color: 'var(--c-disabled)' }}>…</span>
          : <button key={n} type="button" className={n === page ? 'on' : ''} aria-current={n === page ? 'page' : undefined}
            onClick={() => onPage(n)}>{n}</button>)}
        <button type="button" onClick={() => onPage(Math.min(pages, page + 1))} disabled={page >= pages} aria-label="다음 페이지">
          <span className="ms" aria-hidden="true" style={{ fontSize: 'var(--ic-s)' }}>chevron_right</span>
        </button>
        <select className="fi" aria-label="한 페이지에 보일 개수" value={size} onChange={(e) => onSize(Number(e.target.value))}
          style={{ height: 32, marginLeft: 8 }}>
          {sizes.map((n) => <option key={n} value={n}>{n}개씩</option>)}
        </select>
      </span>
    </div>
  )
}
