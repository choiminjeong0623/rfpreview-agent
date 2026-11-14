import { api } from '../api'

type BulkResult = Awaited<ReturnType<typeof api.bulkConfirm>>

// 판정 한꺼번에 확정 (add-bulk-confirm, update-bulk-confirm-guard). 판정 탭과 검토 상세 머리글·아래 행동 줄이 같이 쓴다.

/** 한꺼번에 확정에서 서버가 뺀 이유 */
export const SKIP_REASONS = [['CHECK', '검산'], ['MISMATCH', '숫자 불일치'], ['NO_VALUE', '값 없음']] as const

/** 확정 결과 알림 문장. 뺀 줄이 있으면 수와 이유를 붙인다 */
export function bulkMessage(out: BulkResult): string {
  const left = SKIP_REASONS.map(([k, name]) => [name, out.skipped.filter((x) => x.reason === k).length] as const)
    .filter(([, n]) => n).map(([name, n]) => `${name} ${n}`).join(' · ')
  return `판정 ${out.confirmed}건을 일괄 확정했습니다.` +
    (out.skipped.length ? ` ${out.skipped.length}건은 제외했습니다(${left}). 개별 확인 후 확정하세요.` : '')
}

/** 확정하지 않은 준수 판정 id를 쪽마다 모두 모은다 */
export async function unconfirmedComplyIds(runId: number): Promise<number[]> {
  const ids: number[] = []
  for (let off = 0; ; off += 500) {
    const p = await api.judgmentPage(runId, { result: 'COMPLY', unconfirmed: true, offset: off, limit: 500 })
    ids.push(...p.items.map((j) => j.judgment_id))
    if (off + 500 >= p.total) break
  }
  return ids
}

/** 확정하지 않은 준수 판정을 모두 제안대로 확정하고 알림 문장을 돌려준다 */
export async function confirmAllComply(runId: number, actorId: number): Promise<string> {
  const ids = await unconfirmedComplyIds(runId)
  return bulkMessage(await api.bulkConfirm(runId, ids, actorId))
}
