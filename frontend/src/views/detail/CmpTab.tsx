import { useState } from 'react'
import { api, type CompareRow, type RunSummary } from '../../api'
import { reviewTitle } from '../../components/format'
import { RESULT_NAMES, RESULT_TONES, STAGE_NAMES, STAGE_TONES } from '../../components/labels'
import { useLoad } from '../../components/useLoad'
import { href } from '../../shell/router'

// SCR-08-7 지난 RFP 비교 탭 (목업 v4.57 Detail #cmp). docs/screens/SCR-08-7-지난RFP비교.md
// 같은 고객사(검토 정보의 고객사)의 처리를 마친 지난 검토와 판정 줄을 짝지어 달라진 요구만 보인다 (add-past-compare).
// 짝짓기·구분·판정 비교는 서버 코드가 한다(CR-01). 저장하지 않는다.

type Kind = CompareRow['kind']
type Filter = 'all' | Kind
const KINDS: Record<Kind, [string, string]> = { chg: ['값 바뀜', 'ck chg'], new: ['새로 생김', 'ck new'], del: ['사라짐', 'ck del'] }

function Result({ r }: { r: string | null }) {
  return r ? <span className={`st ${RESULT_TONES[r]}`}>{RESULT_NAMES[r] ?? r}</span> : <span className="st c-grey">요구 없음</span>
}

const ym = (iso: string) => iso.slice(2, 7)

function Compare({ run, otherId }: { run: RunSummary; otherId: number }) {
  const cmp = useLoad(() => api.compare(run.run_id, otherId), [run.run_id, otherId])
  const [f, setF] = useState<Filter>('all')
  if (cmp.error) return <p role="alert">{cmp.error}</p>
  if (!cmp.data) return <p className="dimv">짝짓는 중…</p>
  const { target: t, rows: all, same } = cmp.data
  const n = (k: Kind) => all.filter((r) => r.kind === k).length
  const chips: [Filter, string, number][] = [['all', '달라진 요구', all.length], ['chg', '값 바뀜', n('chg')], ['new', '새로 생김', n('new')], ['del', '사라짐', n('del')]]
  const rows = all.filter((r) => f === 'all' || r.kind === f)
  return (
    <>
      <div className="cmph">
        <div><span className="l">지난 검토</span>
          <b><a href={href(`/reviews/${t.run_id}`)}>{t.review_no}</a> · {reviewTitle(t)}</b>
          <span className="en" style={{ margin: 0 }}>시작 {t.started_at.slice(0, 10)} · 판정 {t.judgments}건{t.products.length ? ` · ${t.products.join(', ')}` : ''}</span></div>
        <span className={`st ${STAGE_TONES[t.stage]}`}>{STAGE_NAMES[t.stage]}</span>
      </div>
      <div className="cmpk">
        {chips.map(([k, label, count]) => (
          <button key={k} type="button" className={f === k ? 'on' : ''} aria-pressed={f === k} onClick={() => setF(k)}><span>{label}</span><b>{count}</b></button>
        ))}
      </div>
      {all.length === 0
        ? <p className="cmempty">지난 검토와 요구 값·판정이 모두 같습니다.</p>
        : <div className="tw"><table className="tbl">
          <thead><tr><th style={{ width: 90 }}>구분</th><th>항목</th><th>지난 RFP</th><th>이번 RFP</th><th>판정 변화</th><th>참고</th></tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={`${r.kind}-${r.equipment}-${r.item_name}-${r.before}-${r.after}-${i}`} className={r.kind === 'del' ? 'cmpd' : undefined}>
                <td><span className={KINDS[r.kind][1]}>{KINDS[r.kind][0]}</span></td>
                <td><b style={{ fontWeight: 600 }}>{r.item_name}</b><div className="en" style={{ margin: 0 }}>{r.equipment}{r.item_raw ? ` · ${r.item_raw}` : ''}</div></td>
                <td style={{ color: 'var(--c-muted)' }}>{r.before}</td>
                <td style={{ fontWeight: 600 }}>{r.after}</td>
                <td style={{ whiteSpace: 'nowrap' }}>
                  {r.kind === 'chg' && <><Result r={r.before_result} />
                    <span className="ms" aria-hidden="true" style={{ fontSize: 14, color: 'var(--c-disabled)', verticalAlign: 'middle' }}>arrow_forward</span></>}
                  {r.kind === 'del' ? <Result r={null} /> : <Result r={r.after_result} />}
                </td>
                <td style={{ color: 'var(--c-text-3)', fontSize: 'var(--fs-sm)' }}>{r.note}</td>
              </tr>
            ))}
          </tbody>
        </table></div>}
      <p className="cmfoot">같은 요구 {same}건은 값과 판정이 지난번과 같아 숨겼습니다.</p>
    </>
  )
}

export function CmpTab({ run }: { run: RunSummary }) {
  const list = useLoad(() => api.compareTargets(run.run_id), [run.run_id, run.customer_name])
  const [picked, setPicked] = useState<number | null>(null)
  const targets = list.data?.targets ?? []
  const id = picked ?? targets[0]?.run_id ?? null
  return (
    <section className="sec" id="cmp">
      <div className="sech">
        <h2>지난 RFP 비교<span className="note">같은 고객사의 지난 검토와 요구사항을 짝지어 달라진 것만 보여 줍니다.</span></h2>
        {targets.length > 0 && <label className="cmpsel">비교 대상
          <select className="fi" value={id ?? ''} onChange={(e) => setPicked(Number(e.target.value))}>
            {targets.map((t) => <option key={t.run_id} value={t.run_id}>{t.review_no} · {reviewTitle(t)} ({ym(t.started_at)})</option>)}
          </select></label>}
      </div>
      {list.error && <p role="alert">{list.error}</p>}
      {list.data && !list.data.customer_name && (
        <p className="cmempty">검토 정보에 고객사를 넣으면 같은 고객사의 지난 검토와 비교합니다. 머리글의 "검토 정보 수정"에서 넣을 수 있습니다.</p>)}
      {list.data?.customer_name && targets.length === 0 && (
        <p className="cmempty">고객사 "{list.data.customer_name}"의 처리를 마친 다른 검토가 없습니다. 같은 고객사로 검토를 등록하면 여기서 비교합니다.</p>)}
      {id !== null && <Compare key={id} run={run} otherId={id} />}
    </section>
  )
}
