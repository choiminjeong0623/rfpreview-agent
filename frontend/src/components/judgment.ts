import type { Judgment, Location, LogEntry, OutputItem, RunDocument, Warranty } from '../api'
import { num } from './format'
import { locationText } from './labels'

// 판정 표·패널·상세 창(SCR-08-1)이 같이 쓰는 표시 형식.

/** 값 + 단위. 값에 단위가 이미 들어 있으면 붙이지 않는다 */
export function withUnit(raw: string | null, unit: string | null): string | null {
  if (raw === null || raw === '') return null
  return unit && !raw.includes(unit) ? `${raw} ${unit}` : raw
}

export function itemName(j: Pick<Judgment, 'item_name' | 'item_name_raw'>): string {
  return j.item_name ?? j.item_name_raw ?? '—'
}

/** 원문 위치 한 곳: 파일 번호 대신 파일 이름 (_공통규칙.md 3장) */
export function locName(loc: Location, docs: RunDocument[] = []): string {
  const name = docs.find((d) => d.file_no === loc.file_no)?.file_name
  const text = locationText(loc)
  return name ? text.replace(/^파일 \d+/, name) : text
}

/** 원문 위치: 첫 위치, 더 있으면 "외 n곳" */
export function locShort(j: Pick<Judgment, 'locations'>, docs: RunDocument[] = []): string {
  const [first, ...rest] = j.locations
  if (!first) return '—'
  return locName(first, docs) + (rest.length ? ` 외 ${rest.length}곳` : '')
}

export function reqText(j: Judgment): string {
  return withUnit(j.req_value_raw, j.unit_raw) ?? '—'
}

/** 제품값 칸: 보증값 작성 줄은 보증값 후보, 나머지는 제품값. sub는 아래 작은 줄 */
export function prodCell(j: Judgment, w?: Warranty): { val: string; sub: string; cls: string } {
  if (j.result === 'WARRANTY_TO_FILL') {
    const v = w ? withUnit(w.candidate_value, w.candidate_unit) : null
    if (v) return { val: v, sub: w!.source_kind === 'ENGINEER' ? '직접 입력' : (w!.product_code ?? '제품표'), cls: '' }
    return { val: '비어 있음', sub: '근거 값 없음', cls: 'c-ora' }
  }
  const val = withUnit(j.product_value_raw, j.product_value_unit) ?? '—'
  const margin = j.margin_value !== null && j.margin_direction !== 'NOT_CALC' && Number(j.margin_value) !== 0
    ? ` · 여유 ${num(Number(j.margin_value))}${j.margin_kind === 'RATIO' ? '배' : ''}` : ''
  return { val, sub: (j.product_code ?? '') + margin + (j.is_assumed ? ' · 팀 가정' : ''), cls: '' }
}

/** 판정 근거의 비교 줄: "요구 4,000 A · 제품 3,150 A" */
export function compareText(j: Judgment, w?: Warranty): string {
  const p = prodCell(j, w)
  return `요구 ${reqText(j)} · 제품 ${p.val}`
}

/** 원문 문장에서 요구값을 찾아 강조할 곳으로 나눈다 [앞, 강조, 뒤] */
export function markSplit(text: string, needle: string | null): [string, string, string] {
  const i = needle ? text.indexOf(needle) : -1
  return i < 0 ? [text, '', ''] : [text.slice(0, i), needle!, text.slice(i + needle!.length)]
}

/** 시스템 제안: 엔지니어가 바꾼 판정이면 처음 바꾸기 전 값, 아니면 지금 값 */
export function suggested(j: Judgment, log: LogEntry[]): string {
  const first = log.find((l) => l.target_table === 'judgment' && l.target_id === j.judgment_id && l.action === 'EDIT')
  return (first?.before_value?.result as string | undefined) ?? j.result
}

/** 담당자 확정: 마지막 확정·수정 기록 (누가, 언제) */
export function confirmedBy(j: Judgment, log: LogEntry[]): LogEntry | null {
  const mine = log.filter((l) => l.target_table === 'judgment' && l.target_id === j.judgment_id
    && (l.action === 'CONFIRM' || l.action === 'EDIT'))
  return mine.length ? mine[mine.length - 1] : null
}

/** 판정에 이어진 목록 항목. 검산 질의처럼 판정 번호가 없는 항목은 같은 요구로 찾는다 */
export function itemFor(items: OutputItem[], j: Judgment): OutputItem | undefined {
  return items.find((i) => i.sources.some((s) => s.judgment_id === j.judgment_id))
    ?? items.find((i) => i.sources.some((s) => s.judgment_id === null && s.requirement_id === j.requirement_id))
}
