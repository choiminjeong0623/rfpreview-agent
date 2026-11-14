import { useEffect, useRef, useState } from 'react'
import { api, type Judgment, type RunDocument, type RunSummary } from '../../api'
import { Pager } from '../../components/Pager'
import { bulkMessage } from '../../components/bulk'
import { CHECK_RULE, checksByRequirement } from '../../components/checks'
import { dueText, isoDay, stamp } from '../../components/format'
import { itemName, locShort, markSplit, prodCell, reqText } from '../../components/judgment'
import { RESULT_DOTS, RESULT_NAMES, RESULT_ORDER, RESULT_TONES, TYPE_NAMES } from '../../components/labels'
import { useLoad } from '../../components/useLoad'
import { currentPath, navigate, pathQuery } from '../../shell/router'
import { useSession } from '../../shell/useSession'
import { filterQuery, parseFilter } from '../../components/judgeFilter'
import { RevisionBar } from './RevisionBar'
import { useToast } from '../../ui'

// SCR-08-1 판정 탭 (목업 v4.57 Detail #judge). docs/screens/SCR-08-1-판정.md
// 판정 칩·거르기·판정 순서 표, 줄을 누르면 판정 상세 화면(add-judgment-view), 줄에 마우스를 올리면 원문 말풍선(update-judge-tab-preview). 고른 줄·준수 모두를 한꺼번에 제안대로 확정 (add-bulk-confirm).
// 공학 검산(FR-12) 위반·확인 필요 줄 표시 (update-check-display). 계산식은 판정 상세 화면.


/** 검색어는 멈춘 뒤 0.3초 있다 보낸다 */
function useDebounced(value: string, ms = 300): string {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return v
}

export function JudgeTab({ run, tick, onChanged }: { run: RunSummary; tick: number; onChanged: () => void }) {
  const { user } = useSession()
  const id = run.run_id
  // 판정 상세 화면에서 돌아오면 주소의 거르기·쪽·보던 줄로 연다
  const [init] = useState(() => {
    const p = pathQuery(currentPath())
    const cur = Number(p.get('cur'))
    return { ...parseFilter(p), cur: Number.isInteger(cur) && cur > 0 ? cur : null }
  })
  const [f, setF] = useState(init.f)
  const [onlyUnc, setOnlyUnc] = useState(init.unc)
  const [onlyPast, setOnlyPast] = useState(init.past)   // 지난 확정과 다른 줄만 (add-review-memory)
  const [onlyRev, setOnlyRev] = useState(!!init.rev)     // 개정에서 바뀐 줄만 (add-revision-notice)
  const [text, setText] = useState(init.q)
  const q = useDebounced(text)
  const [type, setType] = useState(init.type)
  const [page, setPage] = useState(init.page)
  const [size, setSize] = useState(init.size)
  const [cur, setCur] = useState<number | null>(init.cur)
  const [error, setError] = useState<string | null>(null)
  const [sel, setSel] = useState<Record<number, string>>({})   // 고른 판정 id → 판정 (쪽을 넘겨도 남는다)
  const toast = useToast()
  const [busy, setBusy] = useState(false)
  const [tip, setTip] = useState<{ j: Judgment; top: number; left: number; below: boolean } | null>(null)   // 줄 말풍선
  const tipTimer = useRef<number | undefined>(undefined)
  const filters = { result: f === 'all' ? undefined : f, unconfirmed: onlyUnc, q, type_code: type || undefined, past: onlyPast ? 'differs' as const : undefined, revised: onlyRev || undefined }
  const key = JSON.stringify(filters)
  const counts = useLoad(() => api.judgmentCounts(id), [id, tick])
  const rows = useLoad(() => api.judgmentPage(id, { ...filters, order: 'priority', offset: (page - 1) * size, limit: size }),
    [id, key, page, size, tick])
  const warranty = useLoad(() => api.warranty(id, { limit: 500 }), [id, tick])
  const docs = useLoad(() => api.documents(id), [id])
  const checks = useLoad(() => api.checks(id), [id, tick])
  const checkOf = checksByRequirement(checks.data ?? [])
  const violations = (checks.data ?? []).filter((x) => x.result === 'VIOLATION').length
  const unsure = (checks.data ?? []).filter((x) => x.result === 'NEEDS_REVIEW').length
  // 검산 하나는 단시간 전류·최대 순간 전류 두 항목에 표시하므로 꼬리표 붙은 항목 수를 따로 센다 (update-check-banner-rows)
  const marked = (r: string) => [...checkOf.values()].filter((c) => c.result === r).length
  const chkPart = (label: string, n: number, r: string) => `${label} ${n}건(표시한 항목 ${marked(r)}개)`
  const canEdit = run.stage === 'ENGINEER_REVIEW' && user?.role === 'ENGINEER'

  const list = rows.data?.items ?? []
  const total = rows.data?.total ?? 0
  const curRow = list.find((r) => r.judgment_id === cur)          // 판정 상세에서 돌아온 줄을 강조한다
  const wOf = (j: Judgment) => warranty.data?.find((w) => w.judgment_id === j.judgment_id)
  const c = counts.data
  const n = (r: string) => c?.by_result[r] ?? 0
  const chips: [string, string, number][] = [['all', '전체', c?.total ?? 0], ...RESULT_ORDER.map((r): [string, string, number] => [r, RESULT_NAMES[r], n(r)])]

  const reset = (fn: () => void) => { fn(); setPage(1); setCur(null) }
  const clearFilter = () => reset(() => { setF('all'); setOnlyUnc(false); setOnlyPast(false); setOnlyRev(false); setText(''); setType('') })
  // 줄을 누르면 판정 상세 화면. 지금 거르기·쪽을 주소로 넘겨 이전·다음과 목록으로 돌아오기에 쓴다
  const open = (j: Judgment) => navigate(`/reviews/${id}/judgments/${j.judgment_id}${filterQuery({ f, unc: onlyUnc, q: text, type, past: onlyPast, rev: onlyRev, page, size })}`)
  const done = () => { onChanged() }
  const say = (m: string) => toast.done(m)
  // 줄 말풍선 (update-judge-tab-preview): 줄 아래(공간이 없으면 위)에 원문 위치·문장. 고치는 일은 판정 상세 화면
  const showTip = (j: Judgment, el: HTMLElement) => {
    const rc = el.getBoundingClientRect()
    const below = rc.bottom + 140 < window.innerHeight
    setTip({ j, top: below ? rc.bottom + 4 : rc.top - 4, left: Math.min(rc.left + 120, window.innerWidth - 540), below })
  }
  const hideTip = () => { clearTimeout(tipTimer.current); setTip(null) }
  useEffect(() => () => clearTimeout(tipTimer.current), [])
  const selIds = Object.keys(sel).map(Number)
  const selSum = RESULT_ORDER.map((r) => [r, Object.values(sel).filter((v) => v === r).length] as const)
    .filter(([, k]) => k).map(([r, k]) => `${RESULT_NAMES[r]} ${k}`).join(' · ')
  const allSel = list.length > 0 && list.every((j) => sel[j.judgment_id])
  const toggle = (j: Judgment) => setSel((s) => {
    const n = { ...s }
    if (n[j.judgment_id]) delete n[j.judgment_id]; else n[j.judgment_id] = j.result
    return n
  })
  const toggleAll = () => setSel((s) => {
    const n = { ...s }
    list.forEach((j) => { if (allSel) delete n[j.judgment_id]; else n[j.judgment_id] = j.result })
    return n
  })
  const confirmIds = async (ids: number[]) => {
    if (!ids.length) return
    setBusy(true)
    setError(null)
    try {
      const out = await api.bulkConfirm(id, ids, user!.user_id)
      setSel({})
      // 검산 위반·숫자 불일치·값이 빈 줄은 서버가 빼고 확정한다 (update-bulk-confirm-guard)
      say(bulkMessage(out))
      done()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="sec" id="judge">
      <div className="sech"><h2>판정</h2></div>
      {run.revision && <RevisionBar runId={id} revision={run.revision} only={onlyRev} onToggle={() => reset(() => setOnlyRev(!onlyRev))} />}
      <div className="fbar">
        {chips.map(([k, label, cnt]) => (
          <button key={k} type="button" className={'chip' + (f === k ? ' on' : '')} aria-pressed={f === k}
            onClick={() => reset(() => setF(k))}>
            {k !== 'all' && <i style={{ background: RESULT_DOTS[k] }} />}{label}
            {(k === 'DEVIATION_CANDIDATE' || k === 'QUERY_CANDIDATE') && cnt > 0 && <> <span className="n">{cnt}</span></>}
          </button>
        ))}
        {c && (c.past_differs > 0 || onlyPast) && (
          <button type="button" className={'chip' + (onlyPast ? ' on' : '')} aria-pressed={onlyPast} title="다른 검토에서 사람이 같은 요구·같은 제품을 다르게 확정한 줄"
            onClick={() => reset(() => setOnlyPast(!onlyPast))}><i style={{ background: 'var(--c-orange)' }} />지난 확정과 다름 <span className="n">{c.past_differs}</span></button>
        )}
        <span style={{ flex: '1 1 0' }} />
        <label className="sr" htmlFor="jq">판정 검색</label>
        <label className="unc"><input type="checkbox" checked={onlyUnc} onChange={() => reset(() => setOnlyUnc(!onlyUnc))} />미확정만</label>
        <input className="fi" id="jq" value={text} onChange={(e) => { setText(e.target.value); setPage(1); setCur(null) }}
          placeholder="항목명, 영문, 원문 문장" style={{ width: 200 }} />
        <label className="sr" htmlFor="jtype">유형</label>
        <select className="fi" id="jtype" value={type} onChange={(e) => reset(() => setType(e.target.value))}>
          <option value="">모든 유형</option>
          {Object.entries(TYPE_NAMES).map(([code, name]) => <option key={code} value={code}>{name}</option>)}
        </select>
      </div>
      {(violations > 0 || unsure > 0) && (
        <p className="chkn"><span className="ms" aria-hidden="true">calculate</span>
          <span>공학 검산 {[violations ? chkPart('위반', violations, 'VIOLATION') : '', unsure ? chkPart('확인 필요', unsure, 'NEEDS_REVIEW') : ''].filter(Boolean).join(' · ')}
            <span className="en" style={{ display: 'inline', marginLeft: 6 }}>{CHECK_RULE}. 검산 하나는 단시간 전류와 최대 순간 전류 두 항목에 표시합니다. 표시한 항목을 눌러 계산식을 보세요.</span></span></p>
      )}
      <div className="work">
        <div style={{ minWidth: 0 }}>
          {canEdit && selIds.length > 0 && (
            <div className="bulk"><b>{selIds.length}건 선택</b><span className="en" style={{ margin: 0 }}>{selSum}</span><span style={{ flex: '1 1 0' }} />
              <button type="button" className="bo" onClick={() => setSel({})}>선택 해제</button>
              <button type="button" className="bp" disabled={busy} onClick={() => confirmIds(selIds)}><span className="ms" aria-hidden="true" style={{ fontSize: 'var(--ic-s)' }}>done_all</span>제안대로 확정</button></div>
          )}
          <div className="tw">
            <table className="tbl">
              <thead><tr><th style={{ width: 34 }}><input type="checkbox" className="jck" checked={allSel} onChange={toggleAll} disabled={!canEdit} aria-label="표시된 항목 모두 선택" /></th><th style={{ width: 92 }}>판정</th><th>항목</th><th>요구값</th><th>제품값 · 보증값</th><th>원문 위치</th></tr></thead>
              <tbody>
                {list.map((j) => {
                  const p = prodCell(j, wOf(j))
                  return (
                    <tr key={j.judgment_id} className={curRow?.judgment_id === j.judgment_id ? 'cur' : ''} onClick={() => open(j)}
                      tabIndex={0} aria-describedby={tip?.j.judgment_id === j.judgment_id ? 'jtip' : undefined}
                      onKeyDown={(e) => { if (e.key === 'Enter' && e.target === e.currentTarget) open(j) }}
                      onMouseEnter={(e) => { const el = e.currentTarget; clearTimeout(tipTimer.current); tipTimer.current = window.setTimeout(() => showTip(j, el), 400) }}
                      onMouseLeave={hideTip} onFocus={(e) => showTip(j, e.currentTarget)} onBlur={hideTip}>
                      <td onClick={(e) => e.stopPropagation()}><input type="checkbox" className="jck" checked={!!sel[j.judgment_id]} onChange={() => toggle(j)}
                        disabled={!canEdit} aria-label={`${itemName(j)} 선택`} /></td>
                      <td><span className={`st ${RESULT_TONES[j.result]}`}>{RESULT_NAMES[j.result]}</span>
                        {j.revised && <div className="en c-blue" title={`문서 추가(개정 ${run.revision?.no ?? ''})로 ${j.revised === 'CHANGED' ? '판정 값이 바뀐' : '새로 생긴'} 줄`}>{j.revised === 'CHANGED' ? '바뀜(개정)' : '추가(개정)'}</div>}
                        {j.result === 'QUERY_CANDIDATE' && <div className={'en' + (j.query_sent_at ? ' c-blue' : '')} title={j.query_sent_at ? `${j.query_sent_by_name ?? ''} · ${stamp(j.query_sent_at)}` : '고객에게 아직 보내지 않은 질의'}>
                          {j.query_sent_at ? `질의 보냄 · ${dueText(isoDay(new Date(j.query_sent_at)))}` : '질의 초안'}</div>}
                        {j.review_status === 'EDITED' && <div className="en" title="사람이 바꾼 판정">바꿈</div>}
                        {(j.review_status === 'CONFIRMED' || j.review_status === 'EDITED') && <div className="cfm"><span className="ms" aria-hidden="true">check</span>확정</div>}
                        {j.past_decision && <div className={'en past' + (j.past_decision.same ? '' : ' c-ora')} title={`${j.past_decision.review_no}에서 사람이 ${RESULT_NAMES[j.past_decision.result]}(으)로 확정`}>
                          {j.past_decision.same ? `지난 확정 ${RESULT_NAMES[j.past_decision.result]}` : '지난 확정과 다름'}
                          {j.past_decision.match === 'MEANING' && j.past_decision.score != null && ` · 유사도 ${j.past_decision.score.toFixed(2)}`}</div>}
                      </td>
                      <td style={{ minWidth: 180 }}><span style={{ fontWeight: 600 }}>{itemName(j)}</span>
                        {checkOf.get(j.requirement_id) && checkOf.get(j.requirement_id)!.result !== 'PASS' && (
                          <span className={`tag chk ${checkOf.get(j.requirement_id)!.result === 'VIOLATION' ? 'bad' : 'warn'}`}>
                            {checkOf.get(j.requirement_id)!.result === 'VIOLATION' ? '검산 위반' : '검산 확인 필요'}</span>)}
                        {j.item_name && j.item_name_raw && <div className="en">{j.item_name_raw}</div>}</td>
                      <td style={{ whiteSpace: 'nowrap' }}>{reqText(j)}</td>
                      <td style={{ whiteSpace: 'nowrap' }}><span className={p.cls}>{p.val}</span><div className="en">{p.sub}</div></td>
                      <td className="loc">{locShort(j, docs.data ?? [])}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          {rows.data && list.length === 0 && (
            <p style={{ margin: 0, padding: '16px 10px', color: 'var(--c-muted)' }}>조건에 맞는 판정이 없습니다.{' '}
              <button type="button" className="lnk" onClick={clearFilter}>필터 지우기</button></p>
          )}
          {total > 0 && <Pager total={total} page={page} size={size} shown={list.length} onPage={setPage} onSize={(s) => { setSize(s); setPage(1) }} />}
          <div className="tfoot"><span>{list.length}건 표시 · 전체 판정 {c?.total ?? 0}건</span><span>판정 순서: 일탈 후보 → 질의 후보 → 확인 필요 → 보증값 작성 → 준수</span></div>
          {error && <p className="aphint" role="alert">{error}</p>}
        </div>

      </div>
      {tip && <RowTip runId={id} tip={tip} docs={docs.data ?? []} />}
    </section>
  )
}

/** 판정 줄 말풍선: 원문 위치와 원문 문장(요구값 강조). 표 줄이면 표 이름·항목·요구값. 보기만 한다 */
function RowTip({ runId, tip, docs }: { runId: number; tip: { j: Judgment; top: number; left: number; below: boolean }; docs: RunDocument[] }) {
  const { j } = tip
  const req = useLoad(() => api.requirement(j.requirement_id, runId), [j.requirement_id, runId])
  const loc = j.locations[0]
  const [a, m, b] = markSplit(req.data?.text_raw ?? '', j.req_value_raw)
  return (
    <div id="jtip" role="tooltip" className={'jtip' + (tip.below ? '' : ' up')} style={{ top: tip.top, left: tip.left }}>
      <div className="jtip-l">{locShort(j, docs)}</div>
      {loc?.table_name
        ? <p>{loc.table_name}{loc.item_no ? ` ${loc.item_no}번` : ''} · {j.item_name_raw ?? itemName(j)} · <mark>{j.req_value_raw ?? '—'}</mark>{j.unit_raw ? ` ${j.unit_raw}` : ''}</p>
        : <p>{req.data ? <>{a}{m && <mark>{m}</mark>}{b}</> : '원문 불러오는 중…'}</p>}
      <div className="jtip-f">누르면 판정 상세</div>
    </div>
  )
}
