import { describe, expect, it } from 'vitest'
import type { RunListItem, User } from '../api'
import { before, byDue, myTurn } from './myWork'

// 홈 "내가 처리할 건"과 검토 목록 요약 줄이 같은 규칙을 쓴다 (update-home-projects, update-list-my-turn)
const run = (p: Partial<RunListItem>) => ({ stage: 'ENGINEER_REVIEW', engineer_id: 1, approver_id: null, due_date: null, review_no: 'RV-2026-001', ...p }) as RunListItem
const user = (user_id: number, role: string) => ({ user_id, role }) as User

describe('myTurn: 내 차례인 검토', () => {
  it('엔지니어는 내 검토의 담당자 확인·반려·실패와 내가 결재자인 결재 대기', () => {
    const mine = myTurn(user(1, 'ENGINEER'))
    expect(mine(run({ stage: 'ENGINEER_REVIEW' }))).toBe(true)
    expect(mine(run({ stage: 'REJECTED' }))).toBe(true)
    expect(mine(run({ stage: 'FAILED' }))).toBe(true)
    expect(mine(run({ stage: 'ENGINEER_REVIEW', engineer_id: 9 }))).toBe(false)
    expect(mine(run({ stage: 'APPROVAL', engineer_id: 9, approver_id: 1 }))).toBe(true)
    expect(mine(run({ stage: 'APPROVAL', approver_id: 2 }))).toBe(false)
    expect(mine(run({ stage: 'APPROVED' }))).toBe(false)
  })

  it('승인자는 내가 결재자이거나 결재자가 없는 결재 대기만', () => {
    const mine = myTurn(user(2, 'APPROVER'))
    expect(mine(run({ stage: 'APPROVAL', approver_id: 2 }))).toBe(true)
    expect(mine(run({ stage: 'APPROVAL', approver_id: null }))).toBe(true)
    expect(mine(run({ stage: 'APPROVAL', approver_id: 3 }))).toBe(false)
    expect(mine(run({ stage: 'ENGINEER_REVIEW' }))).toBe(false)
  })

  it('견적·품질·영업은 검토 차례가 없고, 사용자를 고르지 않았으면 확인·반려·실패', () => {
    expect(myTurn(user(5, 'COST'))(run({}))).toBe(false)
    expect(myTurn(null)(run({ stage: 'FAILED', engineer_id: 7 }))).toBe(true)
    expect(myTurn(null)(run({ stage: 'APPROVAL' }))).toBe(false)
  })
})

describe('마감 순서', () => {
  it('마감 n일 앞은 달력 기준으로 달을 넘긴다', () => {
    expect(before('2026-12-01', 2)).toBe('2026-11-29')
    expect(before('2026-03-01', 1)).toBe('2026-02-28')
  })

  it('마감이 빠른 순, 마감 없는 검토는 뒤, 같으면 검토 번호 순', () => {
    const rows = [run({ review_no: 'B', due_date: null }), run({ review_no: 'C', due_date: '2026-11-20' }),
      run({ review_no: 'A', due_date: '2026-11-20' }), run({ review_no: 'D', due_date: '2026-11-18' })]
    expect(rows.sort(byDue).map((r) => r.review_no)).toEqual(['D', 'A', 'C', 'B'])
  })
})
