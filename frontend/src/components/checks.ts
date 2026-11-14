import type { EngineeringCheck } from '../api'

// 공학 규칙 검산 표시 (update-check-display, FR-12). 서버가 저장한 값으로 글만 만든다 (CR-01, 화면에서 계산하지 않음).

const RANK: Record<EngineeringCheck['result'], number> = { VIOLATION: 0, NEEDS_REVIEW: 1, PASS: 2 }
export const CHECK_NAMES: Record<EngineeringCheck['result'], string> = { PASS: '통과', VIOLATION: '위반', NEEDS_REVIEW: '확인 필요' }
export const CHECK_TONES: Record<EngineeringCheck['result'], string> = { PASS: 'st c-green', VIOLATION: 'st c-red', NEEDS_REVIEW: 'st c-ora' }
const REASONS: Record<string, string> = {
  NO_FREQUENCY: '같은 표에서 주파수를 찾지 못했습니다',
  MULTI_FREQUENCY: '같은 표에 주파수가 여러 개입니다',
  MULTI_IK: '같은 부위에 단시간 전류가 여러 개입니다',
  UNIT_DIFF: '두 값의 단위가 다릅니다',
}

const ka = (n: number | null) => (n === null ? '—' : `${Number(n.toFixed(2))} kA`)

/** 요구사항 → 가장 나쁜 검산 (최대 순간 전류 줄과 단시간 전류 줄 모두) */
export function checksByRequirement(checks: EngineeringCheck[]): Map<number, EngineeringCheck> {
  const out = new Map<number, EngineeringCheck>()
  for (const c of checks) {
    for (const id of [c.requirement_id, c.ik_requirement_id]) {
      const had = out.get(id)
      if (!had || RANK[c.result] < RANK[had.result]) out.set(id, c)
    }
  }
  return out
}

/** "50 kA × 2.5 = 125 kA" — 확인 필요면 이유 */
export function checkFormula(c: EngineeringCheck): string {
  if (c.result === 'NEEDS_REVIEW' || c.factor === null) return REASONS[c.reason_code ?? ''] ?? '검산할 수 없습니다'
  return `${ka(c.ik_ka)} × ${c.factor} = ${ka(c.expected_ka)}`
}

/** 패널·상세 한 줄: 결과 · 계산식 · 원문 값 */
export function checkLine(c: EngineeringCheck): string {
  const raw = c.peak_raw ? `${c.peak_raw}${/kA/i.test(c.peak_raw) ? '' : ' kA'}` : ka(c.peak_ka)
  if (c.result === 'NEEDS_REVIEW') return `${checkFormula(c)} (단시간 전류 ${ka(c.ik_ka)}, 최대 순간 전류 ${raw})`
  return `${checkFormula(c)} · 원문 최대 순간 전류 ${raw}${c.result === 'VIOLATION' ? ' (계산과 다름)' : ''}`
}

export const CHECK_RULE = '최대 순간 전류 = 단시간(차단) 전류 × 2.5 (50 Hz) 또는 × 2.6 (60 Hz)'
