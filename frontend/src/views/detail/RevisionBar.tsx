import { useState } from 'react'
import type { Revision } from '../../api'
import { stamp } from '../../components/format'
import { revisionText } from '../../components/revision'

// 개정 안내 띠 (SCR-08 v4.96, change add-revision-notice). 문서를 더해 다시 분석한 검토의 판정 탭 위.
// "문서 추가 반영 · 파일 · 판정 n줄 바뀜 · m줄 추가 · k줄 사라짐 · 시각", [바뀐 줄만 보기], 닫기.
// 닫으면 그 개정은 이 브라우저에서 다시 보이지 않는다 (개정 번호마다 기억). 바뀐 줄만 보는 중에는 닫기 대신 띠를 남긴다.

const key = (runId: number, no: number) => `s2w.revbar.${runId}.${no}`

function closed(runId: number, no: number): boolean {
  try { return localStorage.getItem(key(runId, no)) === '1' } catch { return false }
}

export function RevisionBar({ runId, revision, only, onToggle }: { runId: number; revision: Revision; only: boolean; onToggle: () => void }) {
  const [hidden, setHidden] = useState(() => closed(runId, revision.no))
  if (hidden && !only) return null
  const close = () => {
    try { localStorage.setItem(key(runId, revision.no), '1') } catch { /* 저장 못 해도 이번에는 닫는다 */ }
    setHidden(true)
  }
  const some = revision.changed + revision.added > 0
  return (
    <div className="revbar" role="status" aria-label="개정 안내">
      <span className="ms" aria-hidden="true">published_with_changes</span>
      <span><b>문서 추가 반영</b> · {revision.files.join(', ') || '추가 문서'} · {revisionText(revision)} · {stamp(revision.at)}</span>
      <span style={{ flex: '1 1 0' }} />
      {(some || only) && <button type="button" className={'bo' + (only ? ' on' : '')} aria-pressed={only} onClick={onToggle}>{only ? '모든 항목 보기' : '변경 항목만 보기'}</button>}
      {!only && <button type="button" className="ib" aria-label="개정 안내 닫기" title="닫기" onClick={close}><span className="ms" aria-hidden="true">close</span></button>}
    </div>
  )
}
