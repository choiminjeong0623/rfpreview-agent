import type { ItemKey, Product, ProductDetail, ProductUse } from '../api'

// 제품표 칸 표시와 계산 (SCR-16 제품표, SCR-16-1 제품 상세가 같이 쓴다. change add-product-view).
// 빈 칸은 "비어 있음", 그 제품군에 없는 칸은 "—", 팀 가정 값은 "팀 가정" (CR-04, CR-06). 숫자는 같은 칸끼리만 비교한다 (CR-10).

export type Col = { key: keyof Product & string; label: string; unit: string; lower?: boolean }

/** 표의 주요 10칸. lower = 작을수록 강점 (손실, FR-13) */
export const COLS: Col[] = [
  { key: 'rated_voltage_kv', label: '정격 전압', unit: 'kV' },
  { key: 'rated_current_a', label: '정격 전류', unit: 'A' },
  { key: 'short_circuit_ka', label: '단시간 견딤 전류', unit: 'kA' },
  { key: 'peak_current_ka', label: '피크 견딤 전류', unit: 'kA' },
  { key: 'rated_frequency', label: '정격 주파수', unit: 'Hz' },
  { key: 'rated_capacity', label: '정격 용량', unit: '' },
  { key: 'noload_loss_kw', label: '무부하 손실', unit: 'kW', lower: true },
  { key: 'load_loss_kw', label: '부하 손실', unit: 'kW', lower: true },
  { key: 'weight_kg', label: '중량', unit: 'kg' },
]
export const SHORT: Record<string, string> = {
  rated_voltage_kv: '전압 kV', rated_current_a: '정격 전류 A', short_circuit_ka: '단시간 kA', peak_current_ka: '피크 kA', rated_frequency: '주파수 Hz',
  rated_capacity: '용량', noload_loss_kw: '무부하손 kW', load_loss_kw: '부하손 kW', weight_kg: '중량 kg',
}
/** 비교값 칸 (백엔드 products.COMPARISON_COLUMNS). comparison_values_assumed가 참이면 팀 가정 (CR-06) */
export const COMPARISON_COLS: Col[] = [
  { key: 'lightning_impulse_kv', label: '뇌 임펄스 내전압', unit: 'kV' },
  { key: 'power_freq_withstand_kv', label: '상용 주파 내전압', unit: 'kV' },
  { key: 'switching_impulse_kv', label: '개폐 임펄스 내전압', unit: 'kV' },
  { key: 'making_current_ka', label: '투입 전류', unit: 'kA' },
  { key: 'breaking_time_ms', label: '차단 시간', unit: 'ms', lower: true },
  { key: 'closing_time_ms', label: '투입 시간', unit: 'ms', lower: true },
  { key: 'gas_leakage_percent', label: '가스 누설률', unit: '%/년', lower: true },
  { key: 'partial_discharge_pc', label: '부분 방전', unit: 'pC', lower: true },
  { key: 'cooling_type', label: '냉각 방식', unit: '' },
  { key: 'insulation_medium', label: '절연 매질', unit: '' },
  { key: 'maintenance_months', label: '점검 주기', unit: '개월' },
  { key: 'service_life_years', label: '수명', unit: '년' },
]
const COMPARISON = new Set(['peak_current_ka', ...COMPARISON_COLS.map((c) => c.key)])
const LOSS = new Set(['noload_loss_kw', 'load_loss_kw', 'aux_loss_kw'])
/** 정격 탭 칸: 주요 칸(중량 빼고) + 비교값 칸 + 보조 손실 */
export const SPEC_COLS: Col[] = [...COLS.filter((c) => c.key !== 'weight_kg'), ...COMPARISON_COLS,
  { key: 'aux_loss_kw', label: '보조 손실', unit: 'kW', lower: true }]

export type Cell = { text: string; cls: string; sub: string; state: 'na' | 'empty' | 'assume' | 'ok' }

export function fmt(v: unknown): string {
  if (typeof v === 'number') return v.toLocaleString('en-US')
  if (typeof v === 'string' && /^-?\d+(\.\d+)?$/.test(v)) return Number(v).toLocaleString('en-US')
  return String(v)
}

const val = (p: Product | ProductDetail, key: string) => (p as Record<string, unknown>)[key]

/** 칸 하나: 제품군에 없는 칸 "—", 판정에 쓰는데 빈 칸 "비어 있음", 팀 가정이면 아래 줄에 "팀 가정" */
export function cell(p: Product | ProductDetail, key: string): Cell {
  const v = val(p, key)
  if (v === null || v === undefined || v === '') {
    return p.value_columns.includes(key) ? { text: '비어 있음', cls: 'c-ora', sub: '', state: 'empty' } : { text: '—', cls: 'dimv', sub: '', state: 'na' }
  }
  const assumed = p.is_assumed || (LOSS.has(key) && !!p.loss_is_assumed) || (COMPARISON.has(key) && p.comparison_values_assumed)
  const text = key === 'rated_capacity' && p.rated_capacity_unit ? `${fmt(v)} ${p.rated_capacity_unit}` : fmt(v)
  return { text, cls: '', sub: assumed ? '팀 가정' : '', state: assumed ? 'assume' : 'ok' }
}

/** 숫자 값 (없거나 글이면 null) */
export function num(p: Product | ProductDetail, key: string): number | null {
  const v = val(p, key)
  if (typeof v === 'number') return v
  return typeof v === 'string' && /^-?\d+(\.\d+)?$/.test(v) ? Number(v) : null
}

/** 강점 방향: 항목 이름 사전에서 그 제품 칸에 짝지은 항목(pm_column)의 강점 방향. 손실·시간은 작을수록 */
export function strength(c: Col, items: ItemKey[]): string {
  if (c.lower) return '작을수록 강점'
  const s = items.find((i) => i.pm_column === c.key)?.strength_direction
  return s === 'HIGHER' ? '클수록 강점' : s === 'LOWER' ? '작을수록 강점' : '강점 아님'
}

/** 값 종류: 설계 사례 카드 / 팀 가정 / 카탈로그 정격 */
export function valueKind(p: Product | ProductDetail): string {
  if (p.is_design_card) return '설계 사례'
  if (p.is_assumed || p.comparison_values_assumed || p.loss_is_assumed) return '카탈로그 정격 · 일부 팀 가정'
  return '카탈로그 정격'
}

/** 팀 가정 칸 수 (값이 있는 칸 중) */
export function assumedCount(p: ProductDetail): number {
  return [...SPEC_COLS, { key: 'weight_kg' } as Col].filter((c) => cell(p, c.key).state === 'assume').length
}

/** 값이 없어 막힌 판정: 확인 필요 판정 가운데 그 항목이 짝짓는 제품 칸이 비어 있는 줄 (design.md 2) */
export function blocked(p: ProductDetail, items: ItemKey[]): ProductUse[] {
  const col = (k: string | null | undefined) => items.find((i) => i.item_key === k)?.pm_column ?? null
  return p.used_in.filter((u) => u.result === 'NEEDS_REVIEW' && p.empty_columns.includes(col(u.item_key) ?? ''))
}

export type RunUse = { run_id: number; review_no: string; review_name: string | null; due_date: string | null; n: number; by: Partial<Record<string, number>> }

/** 쓰이는 검토: 판정 줄을 검토로 묶어 결과별 수 (최근 검토 먼저) */
export function runUses(p: ProductDetail): RunUse[] {
  const m = new Map<number, RunUse>()
  for (const u of p.used_in) {
    const r: RunUse = m.get(u.run_id) ?? { run_id: u.run_id, review_no: u.review_no, review_name: u.review_name, due_date: u.due_date ?? null, n: 0, by: {} }
    r.n += 1
    r.by[u.result] = (r.by[u.result] ?? 0) + 1
    m.set(u.run_id, r)
  }
  return [...m.values()]
}

/** "준수 n · 일탈 n · 확인 필요 n" */
export function resultCounts(r: RunUse): string {
  const dev = (r.by.DEVIATION_CANDIDATE ?? 0) + (r.by.QUERY_CANDIDATE ?? 0)
  return `준수 ${r.by.COMPLY ?? 0} · 일탈 ${dev} · 확인 필요 ${r.by.NEEDS_REVIEW ?? 0}`
}

/** D-day: 마감까지 남은 날 (지나면 D+n). 마감이 없으면 null */
export function dday(due: string | null, now = new Date()): { text: string; late: boolean } | null {
  if (!due) return null
  const d = new Date(`${due}T00:00:00`)
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const n = Math.round((d.getTime() - today.getTime()) / 86_400_000)
  return { text: n === 0 ? 'D-day' : n > 0 ? `D-${n}` : `D+${-n}`, late: n <= 3 }
}

export type Alt = { code: string; why: string; score: number }

/** 대신 쓸 수 있는 제품 (참고, 판정은 바꾸지 않음): 같은 제품군·정격 전압 같거나 높음,
 * 막힌 칸에 값이 있거나 정격 전류·단시간이 더 높은 제품. 이유 많은 순 → 코드 순, 2개 (design.md 4) */
export function alternatives(p: ProductDetail, same: Product[], items: ItemKey[]): Alt[] {
  const blockCols = new Set(blocked(p, items).map((u) => items.find((i) => i.item_key === u.item_key)?.pm_column).filter(Boolean) as string[])
  const kv = num(p, 'rated_voltage_kv')
  const out: Alt[] = []
  for (const o of same) {
    if (o.product_code === p.product_code || o.is_design_card) continue
    const okv = num(o, 'rated_voltage_kv')
    if (kv !== null && (okv === null || okv < kv)) continue
    const why: string[] = []
    for (const c of blockCols) {
      if (num(o, c) !== null || (val(o, c) ?? '') !== '') why.push(`${[...COLS, ...COMPARISON_COLS].find((x) => x.key === c)?.label ?? c} 값 있음`)
    }
    for (const [key, label, unit] of [['rated_current_a', '정격 전류', 'A'], ['short_circuit_ka', '단시간', 'kA']] as const) {
      const a = num(p, key), b = num(o, key)
      if (a !== null && b !== null && b > a) why.push(`${label} ${fmt(b)} ${unit} (+${fmt(b - a)})`)
    }
    if (why.length) out.push({ code: o.product_code, why: why.join(' · '), score: why.length })
  }
  return out.sort((x, y) => y.score - x.score || x.code.localeCompare(y.code)).slice(0, 2)
}

/** 요구 조건: 정격 전압·정격 전류·단시간 견딤 전류 이상 (design.md 5) */
export type Req = { kv: string; a: string; ka: string }
export const NO_REQ: Req = { kv: '', a: '', ka: '' }
const REQ_COLS: [keyof Req, string, string, string][] = [
  ['kv', 'rated_voltage_kv', '전압', 'kV'], ['a', 'rated_current_a', '정격 전류', 'A'], ['ka', 'short_circuit_ka', '단시간', 'kA'],
]

export const reqOn = (r: Req) => REQ_COLS.some(([k]) => r[k].trim() !== '')

/** 요구 충족 (목업 fitOf): 모두 맞음 / "정격 전류 −850 A" 모자람 / "정격 전류 값 없음" */
export function fit(p: Product, r: Req): { ok: boolean; text: string; cls: string; kind: 'ok' | 'short' | 'none' } {
  const short: string[] = [], none: string[] = []
  for (const [k, col, label, unit] of REQ_COLS) {
    const want = r[k].trim() === '' ? null : Number(r[k])
    if (want === null || Number.isNaN(want)) continue
    const have = num(p, col)
    if (have === null) none.push(`${label} 값 없음`)
    else if (have < want) short.push(`${label} −${fmt(want - have)} ${unit}`)
  }
  if (short.length) return { ok: false, text: short.join(' · '), cls: 'c-ora', kind: 'short' }
  if (none.length) return { ok: false, text: none.join(' · '), cls: 'dimv', kind: 'none' }
  return { ok: true, text: '모두 맞음', cls: 'c-green', kind: 'ok' }
}

/** 요구 조건 요약 "145 kV · 3150 A 이상 · 40 kA 이상" */
export function reqText(r: Req): string {
  return REQ_COLS.filter(([k]) => r[k].trim()).map(([k, , , unit]) => `${r[k].trim()} ${unit} 이상`).join(' · ')
}
