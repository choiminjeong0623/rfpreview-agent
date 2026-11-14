import type { Judgment } from '../api'
import { stamp } from './format'
import { RESULT_NAMES, RESULT_TONES } from './labels'
import { href } from '../shell/router'

/** 판정 출처 표의 "지난 검토" 줄 (add-review-memory). 다른 검토에서 사람이 같은 요구·같은 제품을 본 판정. 힌트일 뿐 */
export function PastDecisionRow({ j }: { j: Judgment }) {
  const p = j.past_decision
  if (!p) return null
  return (
    <tr className="pastrow"><th>지난 검토</th><td><span className={`st ${RESULT_TONES[p.result]}`}>{RESULT_NAMES[p.result]}</span>
      {!p.same && <span className="pvs c-ora">지금과 다름</span>}
      {p.match === 'MEANING' && p.score != null && <span className="pvs" data-testid="past-meaning">유사도 {p.score.toFixed(2)}</span>}
      <span className="pvs"><a href={href(`/reviews/${p.run_id}`)}>{p.review_no}</a>
        {p.decided_by ? ` · ${p.decided_by}` : ''}{p.decided_at ? ` · ${stamp(p.decided_at)}` : ''}</span>
      {p.reason && <div className="en">사유: {p.reason}</div>}
      <div className="en">{p.match === 'MEANING'
        ? '문구는 다르나 요구값·제품이 같고 의미가 매우 유사한 요구사항에 대한 과거 확정 판정입니다. 참고만 하고 판정은 바꾸지 않습니다.'
        : '같은 요구·같은 제품을 사람이 본 판정입니다. 참고만 하고 판정은 바꾸지 않습니다.'}</div></td></tr>
  )
}
