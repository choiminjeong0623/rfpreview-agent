import { describe, expect, it } from 'vitest'
import type { EngineeringCheck } from '../api'
import { checkFormula, checkLine, checksByRequirement } from './checks'

// 공학 검산 표시 (update-check-display, FR-12). 화면은 서버가 저장한 값으로 글만 만든다 (CR-01)
const check = (p: Partial<EngineeringCheck>) => ({
  requirement_id: 1, ik_requirement_id: 2, result: 'PASS', factor: 2.5, ik_ka: 50, expected_ka: 125,
  peak_ka: 125, peak_raw: '125 kA', reason_code: null, ...p,
}) as EngineeringCheck

describe('공학 검산 표시', () => {
  it('계산식: 50 kA × 2.5 = 125 kA', () => {
    expect(checkFormula(check({}))).toBe('50 kA × 2.5 = 125 kA')
  })

  it('확인 필요면 계산식 대신 이유', () => {
    expect(checkFormula(check({ result: 'NEEDS_REVIEW', factor: null, reason_code: 'NO_FREQUENCY' })))
      .toBe('같은 표에서 주파수를 찾지 못했습니다')
    expect(checkFormula(check({ result: 'NEEDS_REVIEW', factor: null, reason_code: 'UNKNOWN' }))).toBe('검산할 수 없습니다')
  })

  it('위반이면 원문 값 뒤에 "계산과 다름", 단위 없는 원문 값에는 kA를 붙인다', () => {
    expect(checkLine(check({ result: 'VIOLATION', peak_raw: '100', peak_ka: 100 })))
      .toBe('50 kA × 2.5 = 125 kA · 원문 최대 순간 전류 100 kA (계산과 다름)')
  })

  it('검산 하나는 최대 순간 전류 줄과 단시간 전류 줄 모두에 붙고, 한 줄에 여럿이면 가장 나쁜 것', () => {
    const map = checksByRequirement([
      check({ requirement_id: 1, ik_requirement_id: 2, result: 'PASS' }),
      check({ requirement_id: 3, ik_requirement_id: 2, result: 'VIOLATION' }),
    ])
    expect(map.get(1)?.result).toBe('PASS')
    expect(map.get(2)?.result).toBe('VIOLATION')
    expect(map.get(3)?.result).toBe('VIOLATION')
  })
})
