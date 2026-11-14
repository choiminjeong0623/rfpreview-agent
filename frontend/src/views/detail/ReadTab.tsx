import { useState } from 'react'
import { api, type ReadCheck, type RunSummary } from '../../api'
import { stamp } from '../../components/format'
import { useLoad } from '../../components/useLoad'
import { usePage } from '../../components/usePage'
import { useSession } from '../../shell/useSession'

// SCR-08-2 문서 읽기 점검 탭 (목업 v4.57 Detail #read). docs/screens/SCR-08-2-문서읽기점검.md
// 점검 줄은 백엔드가 처리 결과(표 칸 역할, 그림 위치, 단위 없는 값, 절 번호)에서 만든다. 화면은 확인 기록만 남긴다.

const KINDS = ['표', '그림', '단위', '위치'] as const
const ICONS: Record<string, string> = { 표: 'table_chart', 그림: 'image', 단위: 'straighten', 위치: 'location_searching' }

export function ReadTab({ run, tick, onChanged }: { run: RunSummary; tick: number; onChanged: () => void }) {
  const { user } = useSession()
  const id = run.run_id
  const checks = useLoad(() => api.readChecks(id), [id, tick])
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const canEdit = run.stage === 'ENGINEER_REVIEW' && user?.role === 'ENGINEER'
  const lock = run.stage !== 'ENGINEER_REVIEW' ? '담당자 확인 단계에서만 확인할 수 있습니다' : !canEdit ? '엔지니어만 확인할 수 있습니다' : undefined

  const rows = checks.data ?? []
  const left = rows.filter((r) => !r.checked_at).length
  const note = KINDS.map((k) => `${k} ${rows.filter((r) => r.kind === k).length}`).join(' · ')
  const { shown, pager } = usePage(rows)

  const toggle = (r: ReadCheck, on: boolean) => {
    setBusy(r.key)
    setError(null)
    ;(on ? api.checkRead(id, r.key, user!.user_id) : api.uncheckRead(id, r.key, user!.user_id))
      .then(onChanged)
      .catch((e: Error) => setError(e.message))
      .finally(() => setBusy(null))
  }

  return (
    <section className="sec" id="read">
      <div className="sech">
        <h2>문서 읽기 점검<span className="note">{note}</span></h2>
        {checks.data && <span className={`st ${left ? 'c-ora' : 'c-green'}`}>{left ? `확인 안 함 ${left}건` : rows.length ? '모두 확인함' : '읽지 못한 곳 없음'}</span>}
      </div>
      {rows.length > 0 && <p className="rdi">분석은 끝났지만 시스템이 제대로 읽지 못한 곳입니다. 여기서 빠진 요구사항은 판정 목록에 나타나지 않으므로, 원문을 직접 확인해 주세요. 확인하지 않은 항목은 결재 요청 사유에 올라갑니다.</p>}
      {checks.error && <p role="alert">{checks.error} <button type="button" className="lnk" onClick={checks.reload}>다시 불러오기</button></p>}
      {/* 0줄 (update-read-check-empty): 사람이 확인한 "모두 확인함"과 헷갈리지 않게 따로 안내한다 */}
      {checks.data?.length === 0 && (
        <div className="rdempty">
          <span className="ms" aria-hidden="true">task_alt</span>
          <div><b>모든 문서를 끝까지 읽었습니다.</b>
            <div>표 칸 역할, 그림, 단위 없는 값, 끊기거나 겹친 절 번호를 살폈고 읽지 못한 곳이 없습니다. 직접 확인할 곳이 없습니다.</div></div>
        </div>
      )}
      {rows.length > 0 && (
        <table className="mini rdt"><tbody>
          {shown.map((r) => (
            <tr key={r.key} className={r.checked_at ? 'done' : undefined}>
              <td style={{ width: 120 }}><span className="rdk"><span className="ms" aria-hidden="true">{ICONS[r.kind]}</span>{r.kind}</span><div className="en">{r.what}</div></td>
              <td>
                <b style={{ fontWeight: 600 }}>{r.loc}</b><div className="en">{r.file_name}</div>
                <div className="rdp">{r.problem}</div>
                <div className="rdtodo"><span className="ms" aria-hidden="true">arrow_right_alt</span>{r.todo}</div>
              </td>
              <td style={{ width: 190, textAlign: 'right' }}>
                {r.checked_at
                  ? <div className="rdok"><span className="st c-green">확인함</span><div className="en">{r.checked_by} · {stamp(r.checked_at)}</div>
                      <span title={lock}><button type="button" className="lnk" style={{ fontSize: 'var(--fs-xs)' }} disabled={!canEdit || busy !== null}
                        onClick={() => toggle(r, false)}>되돌리기</button></span></div>
                  : <span title={lock}><button type="button" className="bo" disabled={!canEdit || busy !== null} onClick={() => toggle(r, true)}>
                      <span className="ms" aria-hidden="true" style={{ fontSize: 16 }}>check</span>직접 확인함</button></span>}
              </td>
            </tr>
          ))}
        </tbody></table>
      )}
      {pager}
      {error && <p className="aphint" role="alert">{error}</p>}
    </section>
  )
}
