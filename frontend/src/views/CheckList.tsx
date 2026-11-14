import type { ApprovalScreen, Criterion } from '../api'
import { checkItems } from '../components/approval'

// 상신 전 확인 목록: 결재 상신 창(SCR-08-10)과 결재 대기 화면(SCR-12)이 같이 쓴다.

const ICONS: Record<string, string> = { ok: 'check', warn: 'error', bad: 'priority_high' }

/** 상신 전 확인 목록. 상신 창은 목업 .apck(설명 줄 있음), 결재 대기 화면은 .wck(한 줄) */
export function CheckList({ found, ratio, listed, unread, compact }: {
  found: Criterion[]; ratio: ApprovalScreen['review_ratio']; listed?: number; unread?: number; compact?: boolean
}) {
  return (
    <ul className={compact ? 'wck' : 'apck'}>
      {checkItems(found, ratio, listed, unread).map((c) => (
        <li key={c.code}>
          <span className={`${compact ? 'wic' : 'apic'} ${c.lv}`}><span className="ms" aria-hidden="true">{ICONS[c.lv]}</span></span>
          {compact ? c.text : <span className="tx">{c.text}<span>{c.sub}</span></span>}
        </li>
      ))}
    </ul>
  )
}
