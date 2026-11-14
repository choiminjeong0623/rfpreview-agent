// 사업 현황 표시 (add-project-status). 범위 상태는 서버가 연결 검토에서 계산한다.
import type { BusinessListItem, BusinessRange } from '../api'

/** 범위 상태 → 이름. 반려는 목업에 없어 더했다 (SCR-04_공유.md) */
export const RANGE_NAMES: Record<BusinessRange['state'], string> = {
  an: '분석 중', fail: '분석 실패', chk: '판정 확인', co: '협조 대기', ap: '결재 대기', rej: '반려', sub: '제출 준비', done: '제출 완료',
}

/** 목업 pj-ch 칩 색. 반려는 분석 실패와 같은 빨강 */
export const RANGE_CHIP: Record<BusinessRange['state'], string> = {
  an: 'an', fail: 'fail', chk: 'chk', co: 'co', ap: 'ap', rej: 'fail', sub: 'sub', done: 'done',
}

/** 사업 상세 범위 카드의 상태 글자 색 */
export const RANGE_TONES: Record<BusinessRange['state'], string> = {
  an: 'st c-grey', fail: 'st c-red', chk: 'st c-blue', co: 'st c-ora', ap: 'st c-grey', rej: 'st c-red', sub: 'st c-green', done: 'st c-green',
}

/** 범위 카드를 누르면 가는 곳과 단추 글자 */
export function rangeGo(r: BusinessRange): { path: string; label: string } {
  if (r.state === 'co') return { path: '/todo', label: '협조 요청 보기' }
  if (r.state === 'fail') return { path: `/reviews/${r.run_id}`, label: '오류 내용 보기' }
  if (r.state === 'ap') return { path: `/reviews/${r.run_id}`, label: '결재 대기 보기' }
  if (r.state === 'rej') return { path: `/reviews/${r.run_id}`, label: '반려 내용 보기' }
  return { path: `/reviews/${r.run_id}`, label: '검토 열기' }
}

/** 내 역할 이름 (엔지니어 → 결재자 → 협조 → 영업 → 만든 사람 중 하나) */
export const BUSINESS_ROLE_NAMES: Record<string, string> = {
  ENGINEER: '엔지니어', APPROVER: '결재자', HELPER: '협조', SALES: '영업', CREATOR: '만든 사람',
}

/** 사업 담당자 표의 역할 */
export const PART_NAMES: Record<string, string> = { ENGINEER: '기술 검토', APPROVER: '결재', HELPER: '협조', SALES: '영업' }

/** 사업 상세 일정 */
export const EVENT_NAMES: Record<string, string> = {
  START: '검토 시작', REQUEST: '결재 상신', APPROVED: '승인', REJECTED: '반려', RUN_DUE: '검토 마감', DUE: '제출 마감', SUBMITTED: '제출 완료',
}

/** 마감 표시: D-3 / D-Day / D+1, 제출 완료면 "제출함" */
export function ddText(b: BusinessListItem): string {
  if (b.submitted_at) return '제출함'
  if (b.days_left == null) return '—'
  return b.days_left < 0 ? `D+${-b.days_left}` : b.days_left === 0 ? 'D-Day' : `D-${b.days_left}`
}

/** 마감 칩 색: 3일 이하 빨강, 7일 이하 주황 (목업 Projects) */
export function ddCls(b: BusinessListItem): string {
  if (b.submitted_at || b.days_left == null) return 'neu'
  return b.days_left <= 3 ? 'neg' : b.days_left <= 7 ? 'crit' : 'neu'
}
