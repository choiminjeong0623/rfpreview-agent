import { Fragment, useState, type ReactNode } from 'react'
import { api, type CommercialImpact, type CostCondition, type Location, type RunDocument, type RunSummary } from '../../api'
import { locName, markSplit } from '../../components/judgment'
import { DOC_KIND_NAMES, locationText } from '../../components/labels'
import { useLoad } from '../../components/useLoad'
import { usePage } from '../../components/usePage'
import { href } from '../../shell/router'

// SCR-08-6 상업 조건 탭 (목업 v4.57 Detail #comm). docs/screens/SCR-08-6-상업조건.md
// FR-16 비용 조건 요약(add-cost-conditions): 비용 영향 유형이 붙은 요구사항을 조항 종류별로 모으고,
// 기술 판단에서 생긴 상업 영향(손실 환산 가산액, 일탈 후보)을 함께 보인다. 금액은 계산하지 않는다.
// 보내기는 협조 요청 현황(SCR-13)에서 한다. 이 탭은 견적 담당 협조 요청 상태만 보인다 (SCR-08-6_공유.md).
// update-comm-tab-layout: 두 표를 같은 네 칸·고정 폭으로, 값 먼저 + 원문 한 줄, 줄을 누르면 원문 전체를 펼친다.

const REQ_ST: Record<string, [string, string]> = {
  TODO: ['미발송', 'st c-grey'], DOING: ['회신 대기', 'st c-blue'], DONE: ['회신 완료', 'st c-green'],
}
const NONE: [string, string] = ['협조 요청 없음', 'st c-grey']

const usd = (n: number) => `$${n.toLocaleString('en-US', { maximumFractionDigits: 0 })}`

/** 줄인 원문 위치: 파일 이름 대신 문서 종류 · 절이나 표 · 행. 종류를 모르면 파일 이름(없으면 파일 n) (update-comm-impact-open) */
function shortLoc(loc: Location, docs: RunDocument[]): string {
  const doc = docs.find((d) => d.file_no === loc.file_no)
  if (!doc || doc.doc_kind === 'UNKNOWN') return locName(loc, docs)
  return locationText(loc).replace(/^파일 \d+/, DOC_KIND_NAMES[doc.doc_kind] ?? doc.doc_kind)
}

/** 펼친 줄 아래: 원문 전체와 모든 원문 위치 */
function Opened({ children, locations, docs }: { children: ReactNode; locations: Location[]; docs: RunDocument[] }) {
  return (
    <tr className="cmopen"><td /><td colSpan={3}>
      <div className="cmfull">{children}</div>
      <ul className="cmlocs">{locations.map((l, i) => <li key={i}>{locName(l, docs)}</li>)}</ul>
    </td></tr>
  )
}

/** 종류 칸의 펼치기 단추 */
function Toggle({ open, onToggle, children }: { open: boolean; onToggle: () => void; children: ReactNode }) {
  return (
    <button type="button" className="cmk cmtg" aria-expanded={open} onClick={(e) => { e.stopPropagation(); onToggle() }}>
      <span className="ms" aria-hidden="true">{open ? 'expand_more' : 'chevron_right'}</span>{children}</button>
  )
}

/** 위치 칸: 줄인 첫 위치 + "외 n곳", 마우스를 올리면 전체 위치 */
function Where({ locations, docs }: { locations: Location[]; docs: RunDocument[] }) {
  const [first, ...rest] = locations
  if (!first) return <td className="loc">—</td>
  return (
    <td className="loc" title={locations.map((l) => locName(l, docs)).join('\n')}>
      {shortLoc(first, docs)}{rest.length > 0 && <span className="cmmore"> 외 {rest.length}곳</span>}
    </td>
  )
}

/** 값을 모두 강조한 원문 */
function Marked({ text, values }: { text: string; values: string[] }) {
  const parts: (string | { k: string })[] = [text]
  for (const v of values) {
    for (let i = 0; i < parts.length; i++) {
      const p = parts[i]
      if (typeof p !== 'string') continue
      const [a, k, b] = markSplit(p, v)
      if (k) { parts.splice(i, 1, a, { k }, b); break }
    }
  }
  return <>{parts.map((p, i) => typeof p === 'string' ? <Fragment key={i}>{p}</Fragment> : <mark key={i}>{p.k}</mark>)}</>
}

/** 같은 상업 영향(종류·제품·가산액·팀 가정·내용)은 한 줄로 묶는다 */
function grouped(list: CommercialImpact[]): { first: CommercialImpact; count: number; locations: Location[] }[] {
  const m = new Map<string, { first: CommercialImpact; count: number; locations: Location[] }>()
  for (const i of list) {
    const key = JSON.stringify([i.kind, i.product_code, i.total_usd, i.is_assumed, i.text])
    const g = m.get(key)
    if (g) { g.count += 1; g.locations.push(...i.locations) } else m.set(key, { first: i, count: 1, locations: [...i.locations] })
  }
  return [...m.values()]
}

function Cols() {
  return <colgroup><col className="c-k" /><col /><col className="c-w" /><col className="c-s" /></colgroup>
}

export function CommTab({ run, tick, onGoJudge, onGoLoss }: {
  run: RunSummary; tick: number; onGoJudge: () => void; onGoLoss: () => void
}) {
  const id = run.run_id
  const data = useLoad(() => api.costConditions(id), [id, tick])
  const docs = useLoad(() => api.documents(id), [id])
  const [kind, setKind] = useState<string | null>(null)
  const [open, setOpen] = useState<string | null>(null)     // 펼친 줄: c-<요구사항> / i-<상업 영향>
  const flip = (k: string) => setOpen(open === k ? null : k)
  const conds = data.data?.conditions ?? []
  const groups = grouped(data.data?.impacts ?? [])
  const cp = usePage(kind ? conds.filter((c) => c.kind === kind) : conds)
  const ip = usePage(groups)
  const pick = (k: string | null) => { setKind(k); cp.reset() }

  if (data.error) return <section className="sec" id="comm"><p role="alert">{data.error} <button type="button" className="lnk" onClick={data.reload}>다시 불러오기</button></p></section>
  if (!data.data) return <section className="sec" id="comm"><p className="dimv">불러오는 중…</p></section>

  const { conditions, impacts } = data.data
  const files = docs.data ?? []
  const kinds = [...new Map(conditions.map((c) => [c.kind, conditions.filter((x) => x.kind === c.kind).length])).entries()]
  const unsent = conditions.filter((c) => c.request_status === 'TODO').length

  return (
    <section className="sec" id="comm">
      <div className="sech">
        <h2>상업 조건<span className="note">비용 조건 {conditions.length} · 기술 판단 영향 {impacts.length}{unsent ? ` · 안 보낸 협조 요청 ${unsent}` : ''}</span></h2>
        {conditions.length > 0 && <a className="bo" href={href('/todo')}>
          <span className="ms" aria-hidden="true" style={{ fontSize: 'var(--ic-s)' }}>forward_to_inbox</span>협조 요청 현황</a>}
      </div>
      <p className="rdi">RFP에서 돈이 드는 조건과 기술 판단에서 생긴 상업 영향입니다. 모두 규칙으로 찾은 <b>후보</b>이고 금액은 계산하지 않습니다.
        받아들일지는 견적 담당이 정하고, 메일은 협조 요청 현황에서 보냅니다.</p>

      <h3 className="cmh">RFP의 비용 조건<span className="cmsub">견적 담당 확인{conditions.length > 0 && ' · 줄을 누르면 원문 전체'}</span></h3>
      {conditions.length === 0
        ? <p className="dimv" style={{ margin: '8px 0' }}>찾은 비용 조건이 없습니다. 상업 조항이 요구사항으로 뽑히지 않은 문서일 수 있습니다.</p>
        : <>
          <div className="fbar" role="group" aria-label="조항 종류">
            <button type="button" className={'chip' + (kind === null ? ' on' : '')} aria-pressed={kind === null} onClick={() => pick(null)}>전체 <span className="n">{conditions.length}</span></button>
            {kinds.map(([k, n]) => (
              <button key={k} type="button" className={'chip' + (kind === k ? ' on' : '')} aria-pressed={kind === k}
                onClick={() => pick(k)}>{k} <span className="n">{n}</span></button>
            ))}
          </div>
          <table className="mini cmt cmfix"><Cols /><tbody>
            {cp.shown.map((c) => <CondRow key={c.requirement_id} c={c} docs={files} open={open === `c-${c.requirement_id}`}
              onToggle={() => flip(`c-${c.requirement_id}`)} />)}
          </tbody></table>
          {cp.pager}
        </>}

      <h3 className="cmh">기술 판단에서 생긴 상업 영향<span className="cmsub">견적 담당 확인{impacts.length > 0 && ' · 줄을 누르면 내용 전체'}</span></h3>
      {impacts.length === 0
        ? <p className="dimv" style={{ margin: '8px 0' }}>손실 환산 결과와 일탈 후보가 없습니다.</p>
        : <table className="mini cmt cmfix"><Cols /><tbody>
          {ip.shown.map(({ first: i, count, locations }) => {
            const k = `i-${i.kind}-${i.loss_calc_id ?? i.item_id}`
            const what = i.kind === 'LOSS'
              ? <>{i.product_code ?? '비교 제품 없음'} · 평가 가격에 {i.total_usd === null ? <span className="c-ora">확인 필요</span> : <b>{usd(i.total_usd)}</b>} 더해짐</>
              : <>일탈을 받아들이거나 옵션으로 맞출 때 가격 영향 확인</>
            return <Fragment key={k}>
            <tr className={'cmrow' + (open === k ? ' on' : '')} onClick={() => flip(k)}>
              <td><Toggle open={open === k} onToggle={() => flip(k)}>{i.kind === 'LOSS' ? '손실 환산 가산액' : '일탈 가격 영향'}</Toggle></td>
              <td>
                <div className="cm1">{what}{open !== k && i.text && <span className="en"> — {i.text}</span>}</div>
                <div className="cmsm">후보{count > 1 ? ` · 같은 조건 ${count}곳` : ''}{i.is_assumed && <span className="tag">팀 가정</span>}</div>
              </td>
              <Where locations={locations} docs={files} />
              <td className="cmst">
                <button type="button" className="lnk" onClick={(e) => { e.stopPropagation(); (i.kind === 'LOSS' ? onGoLoss : onGoJudge)() }}>{i.kind === 'LOSS' ? '손실 환산' : '판정'} →</button>
              </td>
            </tr>
            {open === k && <Opened locations={locations} docs={files}>{i.text ?? what}</Opened>}
            </Fragment>
          })}
        </tbody></table>}
      {ip.pager}
      <p className="cmfoot">견적 담당 협조 요청은 판정을 확정하면 메일로 나가고, <a href={href('/todo')}>협조 요청 현황</a>에서 보내기·회신을 확인할 수 있습니다.</p>
    </section>
  )
}

/** 비용 조건 한 줄: 값 먼저, 원문 한 줄. 누르면 아래에 원문 전체(값 강조)와 모든 위치 */
function CondRow({ c, docs, open, onToggle }: { c: CostCondition; docs: RunDocument[]; open: boolean; onToggle: () => void }) {
  const st = c.request_status ? REQ_ST[c.request_status] : NONE
  return (
    <>
      <tr className={'cmrow' + (open ? ' on' : '')} onClick={onToggle}>
        <td>
          <Toggle open={open} onToggle={onToggle}>{c.kind}</Toggle>
          {c.risk && <div><span className="st c-ora" style={{ marginTop: 4 }}>{c.risk}</span></div>}
          {c.burden && <div><span className="st c-blue" style={{ marginTop: 4 }}>{c.burden}</span></div>}
        </td>
        <td>
          {c.values.length > 0 && <div className="cmv">{c.values.join(' · ')}</div>}
          {!open && <div className="cm1 en">{c.text}</div>}
          <div className="cmsm">후보{c.primary_type_name && c.primary_type !== 'COST' ? ` · 주 유형 ${c.primary_type_name}` : ''}
            {c.repeat_count > 1 ? ` · 같은 조건 ${c.repeat_count}곳` : ''}</div>
        </td>
        <Where locations={c.locations} docs={docs} />
        <td className="cmst"><span className={st[1]}>{st[0]}</span>
          {c.mail_error && <div className="c-red" style={{ fontSize: 'var(--fs-xs)', marginTop: 2 }}>{c.mail_error === '주소 없음' ? '주소 없음' : '발송 실패'}</div>}</td>
      </tr>
      {open && <Opened locations={c.locations} docs={docs}><Marked text={c.text} values={c.values} /></Opened>}
    </>
  )
}
