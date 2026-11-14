import { api, type ApprovalScreen, type Criterion } from '../api'
import { num } from './format'

// 결재 상신 창(SCR-08-10)과 결재 대기 화면(SCR-12)이 같이 쓰는 계산: 검토 요약 칸 건수, 상신 전 확인 줄.

type Ratio = ApprovalScreen['review_ratio']

/** 확인 필요 비율 "21 %" (목업 표기) */
export function ratioText(r: Ratio): string {
  return `${r.total ? Math.round((r.review / r.total) * 100) : 0} %`
}

export const overRatio = (r: Ratio) => r.total > 0 && r.review / r.total > r.threshold

export type Counts = { requirements: number; deviations: number; queries: number; toFill: number; risks: number; loss: string }

/** 요약 칸에 쓰는 건수. 판정 건수는 목록 API의 전체 개수(X-Total-Count)로 받는다 */
export async function loadCounts(runId: number): Promise<Counts> {
  const total = (result: string) => api.judgmentPage(runId, { result, limit: 1 }).then((p) => p.total)
  const [run, deviations, queries, toFill, losses] = await Promise.all([
    api.run(runId), total('DEVIATION_CANDIDATE'), total('QUERY_CANDIDATE'), total('WARRANTY_TO_FILL'), api.losses(runId),
  ])
  const known = losses.length > 0 && losses.every((l) => l.total_usd !== null)
  const loss = known ? `$${num(Math.round(losses.reduce((s, l) => s + (l.total_usd ?? 0), 0)))}` : '—'
  return { requirements: run.requirements, deviations, queries, toFill, risks: run.risks, loss }
}

// 승인 기준마다: 걸리지 않았을 때 문장, 걸렸을 때 덧붙이는 설명. 걸린 내용은 백엔드가 만든 detail을 쓴다
const CHECKS: [string, string, string][] = [
  ['AR-01', '일탈 후보 없음', '일탈 목록 초안에 들어갑니다'],
  ['AR-02', '포괄 조항 없음', '결재자가 원문을 직접 확인해야 합니다'],
  ['AR-03', '', '기준을 넘어 결재자 확인이 필요합니다'],
  ['AR-06', '값 불일치·풀리지 않은 질의 없음', '질의서 초안에 들어갑니다'],
  ['AR-07', '목록에 빠진 일탈 없음', '일탈 목록에 넣거나 판정을 고쳐 주세요'],
  ['AR-08', '전달할 제안 포인트 없음', '채택한 것만 영업·견적 담당에게 전달합니다'],
]

/** listed: 일탈 목록에 들어간 수 (누락 점검). 주면 AR-01 줄에 붙인다 */
export function checkItems(found: Criterion[], ratio: Ratio, listed?: number, unread?: number) {
  const items = CHECKS.map(([code, okText, sub]) => {
    const hit = found.find((c) => c.ar_code === code)
    const pct = ratioText(ratio)
    const okLine = code === 'AR-03' ? `확인 필요 ${pct} (기준 ${Math.round(ratio.threshold * 100)} % 이하)` : okText
    const lv = !hit ? 'ok' : code === 'AR-01' ? 'bad' : 'warn'
    // AR-03: 직접 작성할 칸(제품표에 연결되지 않은 보증값 빈칸)은 비율에서 뺐다는 것을 적는다
    const handFill = code === 'AR-03' && ratio.hand_fill ? ` · 직접 작성할 칸 ${ratio.hand_fill}개는 뺌` : ''
    const text = (hit ? hit.detail + (code === 'AR-01' && listed !== undefined ? ` · 일탈 목록에 ${listed}건` : '') : okLine) + handFill
    return { code, lv, text, sub: hit ? sub : '' }
  })
  if (unread === undefined) return items
  // 문서 읽기 점검 (SCR-08-2): 승인 기준은 아니지만 목업처럼 확인 비율 줄 다음에 둔다. 남아 있어도 상신할 수 있다
  const read = unread
    ? { code: 'READ', lv: 'warn', text: `문서 읽기 점검 미확인 ${unread}건`, sub: '빠진 요구사항이 있을 수 있습니다' }
    : { code: 'READ', lv: 'ok', text: '문서 읽기 점검 모두 확인', sub: '' }
  const at = items.findIndex((c) => c.code === 'AR-03') + 1
  return [...items.slice(0, at), read, ...items.slice(at)]
}
