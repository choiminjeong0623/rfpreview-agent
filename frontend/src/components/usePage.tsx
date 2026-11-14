import { useState } from 'react'
import { Pager } from './Pager'

// 검토 상세 탭 목록 쪽 나누기 (update-detail-tab-paging). 화면에서 자르고, 줄 수가 쪽 크기보다 많을 때만 쪽 번호 줄을 그린다.
// 목록이 줄어 지금 쪽이 없어지면(확인·닫기 뒤 다시 불러옴) 마지막 쪽으로 맞춘다.
export function usePage<T>(list: T[], first = 10) {
  const [page, setPage] = useState(1)
  const [size, setSize] = useState(first)
  const pages = Math.max(1, Math.ceil(list.length / size))
  const cur = Math.min(page, pages)
  const shown = list.slice((cur - 1) * size, cur * size)
  const pager = list.length > first
    ? <Pager total={list.length} page={cur} size={size} shown={shown.length} onPage={setPage} onSize={(n) => { setSize(n); setPage(1) }} />
    : null
  return { shown, pager, reset: () => setPage(1) }
}
