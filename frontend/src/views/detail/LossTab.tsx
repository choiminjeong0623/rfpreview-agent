import { useRef, useState } from 'react'
import { api, type Loss, type RunDocument, type RunSummary } from '../../api'
import { num } from '../../components/format'
import { locName } from '../../components/judgment'
import { useLoad } from '../../components/useLoad'
import { useSession } from '../../shell/useSession'

// SCR-08-4 손실 환산 탭 (목업 v4.57 Detail #loss). docs/screens/SCR-08-4-손실환산.md
// 가산액은 백엔드가 계산한 값(amounts, total_usd)만 보인다 (CR-01). 손실값을 넣으면 PUT으로 다시 계산한다.

const KINDS = [
  ['noload', '무부하 손실', 'price_noload', 'loss_noload_kw'],
  ['load', '부하 손실', 'price_load', 'loss_load_kw'],
  ['aux', '보조 손실', 'price_aux', 'loss_aux_kw'],
] as const
type Field = (typeof KINDS)[number][3]

const REASONS: Record<string, string> = {
  NO_PRODUCT: '비교 제품이 없어 손실값이 비어 있습니다. 손실값을 넣으면 팀 가정으로 계산합니다.',
  NO_LOSS_VALUE: '손실값이 모두 있어야 가산액을 계산합니다.',
  PRICE_UNIT: '단가 단위가 $/kW가 아니어서 계산하지 않습니다 (단위 환산 안 함).',
}

const usd = (v: number | null) => (v === null ? '—' : `$${num(Math.round(v))}`)

// 화면에 보이는 값이 모두 같은 단가 표는 한 상자로 묶는다 (update-loss-tab-group). 계산은 표마다 백엔드가 한다
const sameKey = (l: Loss) => JSON.stringify([l.price_noload, l.price_load, l.price_aux, l.price_unit, l.product_code,
  l.loss_noload_kw, l.loss_load_kw, l.loss_aux_kw, l.is_assumed, l.reason_code])
function grouped(list: Loss[]): Loss[][] {
  const m = new Map<string, Loss[]>()
  for (const l of list) m.set(sameKey(l), [...(m.get(sameKey(l)) ?? []), l])
  return [...m.values()]
}

function lines(l: Loss): string {
  const ns = l.price_locations.map((p) => p.line_start).filter((n): n is number => n !== null)
  if (!ns.length) return ''
  const [a, b] = [Math.min(...ns), Math.max(...ns)]
  return a === b ? `단가 ${a}행` : `단가 ${a}~${b}행`
}

export function LossTab({ run, tick, onChanged, onGoBid }: { run: RunSummary; tick: number; onChanged: () => void; onGoBid: () => void }) {
  const { user } = useSession()
  const id = run.run_id
  const losses = useLoad(() => api.losses(id), [id, tick])
  const docs = useLoad(() => api.documents(id), [id])
  const canEdit = run.stage === 'ENGINEER_REVIEW' && user?.role === 'ENGINEER'
  const lock = run.stage !== 'ENGINEER_REVIEW' ? '담당자 확인 단계에서만 고칠 수 있습니다' : !canEdit ? '엔지니어만 고칠 수 있습니다' : undefined
  const list = losses.data ?? []
  const first = list[0]
  const assumed = list.some((l) => l.is_assumed)
  const note = [first && lines(first), assumed && '손실값은 팀 가정'].filter(Boolean).join(' · ')
  const clause = first?.locations[0]

  return (
    <section className="sec" id="loss">
      <div className="sech">
        <h2>손실 환산 (참고값){note && <span className="note">{note}</span>}</h2>
        {/* 협조 요청은 입찰 영향 탭에서 손실 환산 제안 포인트를 채택하면 견적 담당에게 간다. 이 단추는 그 탭으로 옮긴다 */}
        <button type="button" className="bo" onClick={onGoBid}
          title="입찰 영향 탭에서 손실 환산 제안 포인트를 채택하면 견적 담당에게 협조 요청이 갑니다">견적 담당에 협조 요청 <span aria-hidden="true">→</span></button>
      </div>
      {losses.error && <p role="alert">{losses.error} <button type="button" className="lnk" onClick={losses.reload}>다시 불러오기</button></p>}
      {losses.data?.length === 0 && (
        <div className="lsnote"><span className="ms" aria-hidden="true">info</span>
          <span>이 RFP에는 손실 환산 조항이 없어 계산하지 않았습니다. 손실 환산은 고객이 단가($/kW) 조항을 둔 경우에만 계산하는 변압기 참고값입니다.</span></div>
      )}
      {first && (
        <div className="lsnote"><span className="ms" aria-hidden="true">info</span>
          <span><b>고객이 손실 환산 조항을 둔 경우에만 계산하는 변압기 참고값입니다.</b> 이 RFP는 {clause ? locName(clause, docs.data ?? []) : '데이터시트'}에 손실 환산 단가가 있어
            계산했습니다. 조항이 없는 RFP에서는 계산하지 않습니다. 콘덴서 용량이나 전기실 전체 손실 계산은 하지 않습니다.</span></div>
      )}
      {grouped(list).map((g) => <LossTable key={g[0].loss_calc_id} runId={id} group={g} many={list.length > 1} docs={docs.data ?? []}
        canEdit={canEdit} lock={lock} onDone={onChanged} />)}
    </section>
  )
}

function LossTable({ runId, group, many, docs, canEdit, lock, onDone }: {
  runId: number; group: Loss[]; many: boolean; docs: RunDocument[]; canEdit: boolean; lock?: string; onDone: () => void
}) {
  const l = group[0]
  const initial = () => Object.fromEntries(KINDS.map(([, , , f]) => [f, l[f] === null ? '' : String(Number(l[f]))])) as Record<Field, string>
  const [vals, setVals] = useState(initial)
  const [error, setError] = useState<string | null>(null)
  // 칸을 옮겨 가며 넣는 동안 저장이 겹치지 않게 차례로 보낸다 (입력 칸은 막지 않는다)
  const queue = useRef(Promise.resolve())
  const sent = useRef('')
  const save = () => {
    const changed = KINDS.some(([, , , f]) => vals[f].trim() !== (l[f] === null ? '' : String(Number(l[f]))))
    if (!changed) return
    const body: Record<string, number | null> = {}
    for (const [, name, , f] of KINDS) {
      const v = vals[f].trim()
      const n = v === '' ? null : Number(v)
      if (n !== null && (!Number.isFinite(n) || n < 0)) { setError(`${name} 손실값은 0 이상의 숫자로 넣어 주세요.`); return }
      body[f] = n
    }
    const key = JSON.stringify(body)
    if (key === sent.current) return
    sent.current = key
    setError(null)
    // 묶인 표마다 같은 손실값을 차례로 저장한다
    queue.current = queue.current.then(async () => { for (const x of group) await api.updateLoss(runId, x.loss_calc_id, body) })
      .then(onDone, (e: Error) => setError(e.message))
  }
  const hint = l.reason_code ? REASONS[l.reason_code] : null

  return (
    <>
      <div className="en" style={{ margin: '12px 0 6px' }}>
        {group.length > 1 && <b>같은 조건 {group.length}곳 · </b>}
        {many && group.length === 1 && l.locations[0] && `${locName(l.locations[0], docs)} · `}비교 제품 {l.product_code ?? '없음'}
        {l.is_assumed && <span className="st c-ora" style={{ marginLeft: 8 }}>팀 가정</span>}
        {group.length > 1 && <ul style={{ margin: '4px 0 0', paddingLeft: 18 }}>
          {group.map((x) => x.locations[0] && <li key={x.loss_calc_id}>{locName(x.locations[0], docs)}</li>)}</ul>}
      </div>
      <div className="tw">
      <table className="mini" style={{ maxWidth: 640 }}>
        <tbody>
          {KINDS.map(([k, name, price, f]) => (
            <tr key={k}>
              <td>{name}</td>
              <td style={{ textAlign: 'right', color: 'var(--c-muted)' }}>{num(Number(l[price]))} {l.price_unit ?? ''} ×</td>
              <td style={{ textAlign: 'right' }}>
                <label className="sr" htmlFor={`loss-${l.loss_calc_id}-${k}`}>{name} 손실값 (kW)</label>
                <input className="fi" id={`loss-${l.loss_calc_id}-${k}`} inputMode="decimal" value={vals[f]} disabled={!canEdit} title={lock}
                  onChange={(e) => setVals({ ...vals, [f]: e.target.value })} onBlur={save}
                  onKeyDown={(e) => { if (e.key === 'Enter') save() }} style={{ width: 72, textAlign: 'right' }} /> kW
              </td>
              <td style={{ textAlign: 'right' }}>{l.amounts[k] === null ? <span className="c-ora">입력 필요</span> : usd(l.amounts[k])}</td>
            </tr>
          ))}
          <tr><td style={{ fontWeight: 700 }}>가산액</td><td /><td /><td style={{ textAlign: 'right', fontWeight: 700 }}>{usd(l.total_usd === null ? null : Number(l.total_usd))}</td></tr>
        </tbody>
      </table>
      </div>
      {hint && <p className="en" style={{ marginTop: 6 }}>{hint}</p>}
      {error && <p className="aphint" role="alert">{error}</p>}
    </>
  )
}
