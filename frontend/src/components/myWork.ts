import type { RunListItem, User } from '../api'
import { isoDay } from './format'

// 홈 "내 차례" 계산 (SCR-03 v4.96, change update-home-projects design.md 1·2).
// 나의 업무 "내가 처리할 건"과 오늘 할 일이 같은 목록을 쓴다 (9단계 요약 상자도 이 수와 같아야 한다).

export const REVIEWING = (r: RunListItem) => r.stage === 'ENGINEER_REVIEW' || r.stage === 'REJECTED' || r.stage === 'FAILED'

/** 내 차례인 검토 (design.md 1): 엔지니어 = 내 검토 중 판정 확인·반려·실패 + 내가 결재자인 결재 대기,
 * 승인자 = 내가 결재자인(결재자 없으면 모든) 결재 대기, 견적·품질·영업 = 없음. 사용자를 고르지 않았으면 판정 확인·반려·실패 */
export function myTurn(user: User | null): (r: RunListItem) => boolean {
  if (!user) return REVIEWING
  const me = user.user_id
  const approving = (r: RunListItem) => r.stage === 'APPROVAL' && r.approver_id === me
  if (user.role === 'ENGINEER') return (r) => (r.engineer_id === me && REVIEWING(r)) || approving(r)
  if (user.role === 'APPROVER') return (r) => r.stage === 'APPROVAL' && (r.approver_id === me || r.approver_id === null)
  return () => false
}

/** 마감 날짜에서 n일 앞 (YYYY-MM-DD) */
export function before(due: string, n: number): string {
  const [y, m, d] = due.split('-').map(Number)
  return isoDay(new Date(y, m - 1, d - n))
}

/** 오늘 할 일 순서 (design.md 2): 상신 권장일(= 마감 2일 전)·마감 빠른 순, 없으면 뒤, 같으면 검토 번호 */
export function byDue(a: RunListItem, b: RunListItem): number {
  return (a.due_date ?? '9999').localeCompare(b.due_date ?? '9999') || a.review_no.localeCompare(b.review_no)
}

