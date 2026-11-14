// 표 아래 페이지 번호에 보일 번호 (Pager).

/** 보일 페이지 번호. null은 "…" 자리 */
export function pageItems(page: number, pages: number): (number | null)[] {
  if (pages <= 9) return Array.from({ length: pages }, (_, i) => i + 1)
  const from = Math.max(2, Math.min(page - 2, pages - 5))
  const to = Math.min(pages - 1, Math.max(page + 2, 6))
  const middle = Array.from({ length: to - from + 1 }, (_, i) => from + i)
  return [1, ...(from > 2 ? [null] : []), ...middle, ...(to < pages - 1 ? [null] : []), pages]
}
