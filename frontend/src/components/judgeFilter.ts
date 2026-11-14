import type { JudgmentQuery } from '../api'

// 판정 목록 거르기를 주소에 담는다 (add-judgment-view). 판정 탭 ↔ 판정 상세 화면이 같은 거르기·같은 쪽을 쓴다.
// 주소 예: #/reviews/12/judgments/345?f=DEVIATION_CANDIDATE&unc=1&page=2&size=10

export type JudgeFilter = { f: string; unc: boolean; q: string; type: string; past: boolean; rev?: boolean; page: number; size: number }

export const DEFAULT_FILTER: JudgeFilter = { f: 'all', unc: false, q: '', type: '', past: false, page: 1, size: 10 }

const pos = (v: string | null, d: number) => {
  const n = Number(v)
  return Number.isInteger(n) && n > 0 ? n : d
}

export function parseFilter(p: URLSearchParams): JudgeFilter {
  return {
    f: p.get('f') || 'all', unc: p.get('unc') === '1', q: p.get('q') ?? '', type: p.get('type') ?? '',
    past: p.get('past') === '1', rev: p.get('rev') === '1', page: pos(p.get('page'), 1), size: pos(p.get('size'), 10),
  }
}

/** 기본값과 다른 칸만 주소에 넣는다 */
export function filterQuery(f: JudgeFilter, extra: Record<string, string | number> = {}): string {
  const p = new URLSearchParams()
  if (f.f !== 'all') p.set('f', f.f)
  if (f.unc) p.set('unc', '1')
  if (f.q) p.set('q', f.q)
  if (f.type) p.set('type', f.type)
  if (f.past) p.set('past', '1')
  if (f.rev) p.set('rev', '1')
  if (f.page !== 1) p.set('page', String(f.page))
  if (f.size !== 10) p.set('size', String(f.size))
  Object.entries(extra).forEach(([k, v]) => p.set(k, String(v)))
  const s = p.toString()
  return s ? `?${s}` : ''
}

/** 판정 목록 API 거르기 (판정 탭 표와 같은 값) */
export function filterParams(f: JudgeFilter): JudgmentQuery {
  return { result: f.f === 'all' ? undefined : f.f, unconfirmed: f.unc, q: f.q, type_code: f.type || undefined,
    past: f.past ? 'differs' : undefined, revised: f.rev || undefined }
}

/** 거른 목록의 n번째(1부터)가 있는 쪽 */
export function pageOf(n: number, size: number): number {
  return Math.max(1, Math.ceil(n / size))
}
