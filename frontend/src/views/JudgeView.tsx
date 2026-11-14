import { useEffect, useState } from 'react'
import { api, type CompareRule, type Judgment, type Location, type RunDocument } from '../api'
import { PastDecisionRow } from '../components/PastDecisionRow'
import { TypeFix } from '../components/TypeFix'
import { CheckCalc } from '../components/CheckCalc'
import { CHECK_NAMES, checkLine, checksByRequirement } from '../components/checks'
import { dueText, isoDay, reviewTitle, stamp } from '../components/format'
import { filterParams, filterQuery, pageOf, parseFilter, type JudgeFilter } from '../components/judgeFilter'
import { compareText, confirmedBy, itemFor, itemName, markSplit, prodCell, reqText, suggested } from '../components/judgment'
import { DIRECTION_NAMES, RESULT_NAMES, RESULT_ORDER, RESULT_TONES, STAGE_NAMES, locationText } from '../components/labels'
import { useLoad } from '../components/useLoad'
import { useCrumbTail } from '../shell/crumb'
import { usePageCss } from '../shell/pageCss'
import { href, navigate, pathQuery, useHashPath } from '../shell/router'
import { useSession } from '../shell/useSession'
import { Button, ErrorBox, Loading, Modal, useToast } from '../ui'
import { OutputEditor } from './detail/OutputEditor'

// SCR-08-12 판정 상세 화면 (목업 v4.96 JudgeView, change add-judgment-view). docs/screens/SCR-08-12-판정상세.md
// 주소: #/reviews/:id/judgments/:jid?<판정 목록 거르기>. 이전·다음은 같은 거르기의 판정 순서.
// 화면은 값을 비교·계산하지 않는다 (CR-01). 질의 보냄 표시는 add-query-sent에서 더한다.

const LANGS: Record<string, string> = { en: 'EN · 영어', ko: 'KO · 한국어', image: '이미지' }
/** 비교 방향 → 요구값과 제품값 사이 부등호 (요구 ? 제품). GE는 제품이 요구 이상이어야 하므로 "≤" */
const OPS: Record<string, string> = { GE: '≤', LE: '≥', LT: '>', EQ: '=', IN: '⊆' }
const WINDOW = 500           // 이전·다음을 정하는 거른 목록 창 (서버 상한, design.md 4)
const AROUND = 2             // 원문 위치 앞뒤 줄 수
const MAX_LINES = 40

/** 판정 항목의 비교 규칙: 같은 표 이름 줄을 먼저, 없으면 같은 항목 */
function ruleFor(rules: CompareRule[], j: Judgment, loc?: Location): CompareRule | undefined {
  if (!j.item_key) return undefined
  const same = rules.filter((r) => r.item_key === j.item_key)
  return same.find((r) => loc?.table_name && r.table_name === loc.table_name) ?? same[0]
}

function lockReason(stage: string, role: string | undefined): string | null {
  if (stage !== 'ENGINEER_REVIEW') return `${STAGE_NAMES[stage] ?? stage} 중에는 고칠 수 없습니다`
  if (role !== 'ENGINEER') return '기술 검토 엔지니어만 고칠 수 있습니다'
  return null
}

export function JudgeView({ runId, judgmentId }: { runId: number; judgmentId: number }) {
  usePageCss('Detail')
  usePageCss('JudgeView')
  const path = useHashPath()
  const filter = parseFilter(pathQuery(path))
  const key = filterQuery(filter)
  const win = Math.floor(((filter.page - 1) * filter.size) / WINDOW) * WINDOW
  const [tick, setTick] = useState(0)
  const run = useLoad(() => api.run(runId), [runId])
  // filter는 주소(key)로 바뀐다
  const list = useLoad(() => api.judgmentPage(runId, { ...filterParams(filter), order: 'priority', offset: win, limit: WINDOW }),
    [runId, key, win, tick])
  const docs = useLoad(() => api.documents(runId), [runId])
  const items = list.data?.items ?? []
  const idx = items.findIndex((j) => j.judgment_id === judgmentId)
  const j = idx >= 0 ? items[idx] : null
  const pos = win + idx + 1
  const total = list.data?.total ?? 0

  const go = (target: Judgment, n: number, f: JudgeFilter = filter) =>
    navigate(`/reviews/${runId}/judgments/${target.judgment_id}${filterQuery({ ...f, page: pageOf(n, f.size) })}`, { replace: true })
  const back = () => navigate(`/reviews/${runId}${filterQuery({ ...filter, page: j ? pageOf(pos, filter.size) : filter.page },
    { cur: judgmentId })}`)
  // 창 밖 이웃은 한 줄만 더 불러 정한다 (창 끝에서 ↑↓)
  const step = async (d: -1 | 1) => {
    const n = pos + d
    if (n < 1 || n > total) return
    const inWin = items[idx + d]
    const target = inWin ?? (await api.judgmentPage(runId, { ...filterParams(filter), order: 'priority', offset: n - 1, limit: 1 })).items[0]
    if (target) go(target, n)
  }
  const prev = j && pos > 1 ? () => void step(-1) : null
  const next = j && pos < total ? () => void step(1) : null

  const [editing, setEditing] = useState(false)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (editing) return                         // 판정 바꾸기 창이 Esc를 받는다
      if (e.target instanceof HTMLTextAreaElement || e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement) return
      if (e.key === 'Escape') back()
      if (e.key === 'ArrowUp' && prev) { e.preventDefault(); prev() }
      if (e.key === 'ArrowDown' && next) { e.preventDefault(); next() }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  const r = run.data
  useCrumbTail(r?.review_no)
  const ctx = r ? `${reviewTitle(r)} · ${r.review_no}` : ''
  return (
    <div className="jv">
      <div className="jv-top">
        <a className="jv-back" href={href(`/reviews/${runId}${filterQuery({ ...filter, page: j ? pageOf(pos, filter.size) : filter.page }, { cur: judgmentId })}`)}>
          <span className="ms" aria-hidden="true">arrow_back</span>판정 목록으로</a>
        <span className="jv-ctx">{ctx}</span>
      </div>
      {list.error && <ErrorBox error={list.error} onRetry={list.reload} />}
      {!list.data && !list.error && <Loading label="판정 불러오는 중" />}
      {list.data && !j && (
        <div className="uiempty" role="status">이 검토에 없는 판정입니다. <a href={href(`/reviews/${runId}`)}>판정 목록으로</a></div>
      )}
      {r && j && (
        <Detail key={j.judgment_id} runId={runId} stage={r.stage} j={j} docs={docs.data ?? []} pos={pos} total={total}
          onPrev={prev} onNext={next} editing={editing} setEditing={setEditing}
          onChanged={() => setTick((t) => t + 1)}
          onConfirmed={() => {
            // 다음 확정 안 한 판정으로 (창 안에서 찾고, 없으면 그대로 다시 불러온다)
            const k = items.findIndex((x, i) => i > idx && x.review_status === 'CANDIDATE')
            if (k >= 0) go(items[k], win + k + 1)
            else setTick((t) => t + 1)
          }} />
      )}
    </div>
  )
}

type DetailProps = {
  runId: number; stage: string; j: Judgment; docs: RunDocument[]; pos: number; total: number
  onPrev: (() => void) | null; onNext: (() => void) | null
  editing: boolean; setEditing: (v: boolean) => void; onChanged: () => void; onConfirmed: () => void
}

function Detail({ runId, stage, j, docs, pos, total, onPrev, onNext, editing, setEditing, onChanged, onConfirmed }: DetailProps) {
  const { user } = useSession()
  const toast = useToast()
  const [occ, setOcc] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [wVal, setWVal] = useState('')      // 보증값 직접 입력 (update-judge-tab-preview, 판정 탭 패널에서 옮김)
  const [wWhy, setWWhy] = useState('')
  const req = useLoad(() => api.requirement(j.requirement_id, runId), [j.requirement_id, runId])
  const log = useLoad(() => api.history(runId), [runId, j.review_status, j.result])
  const outputs = useLoad(() => api.outputs(runId), [runId, j.review_status, j.result])
  const checks = useLoad(() => api.checks(runId), [runId])
  const rules = useLoad(() => api.compareRules(), [])
  const product = useLoad(() => (j.product_code ? api.product(j.product_code) : Promise.resolve(null)), [j.product_code])
  const warranty = useLoad(() => (j.result === 'WARRANTY_TO_FILL' ? api.warranty(runId, { limit: 500 }) : Promise.resolve(null)), [runId, j.result])

  const loc = j.locations[Math.min(occ, j.locations.length - 1)]
  const doc = docs.find((d) => d.file_no === loc?.file_no)
  const w = warranty.data?.find((x) => x.judgment_id === j.judgment_id)
  const p = prodCell(j, w)
  const sug = suggested(j, log.data ?? [])
  const conf = j.review_status === 'CONFIRMED' || j.review_status === 'EDITED' ? confirmedBy(j, log.data ?? []) : null
  const draft = itemFor(outputs.data ?? [], j)
  const check = checksByRequirement(checks.data ?? []).get(j.requirement_id)
  const rule = ruleFor(rules.data ?? [], j, loc)
  const lock = lockReason(stage, user?.role)
  const isQuery = j.result === 'QUERY_CANDIDATE'
  const saveW = () => {
    if (!w || !user) return
    setError(null)
    api.act(runId, { target: 'warranty_candidate', target_id: w.candidate_id, action: 'EDIT', value: { value: wVal.trim() }, reason: wWhy.trim(), actor_id: user.user_id })
      .then(() => { setWVal(''); setWWhy(''); warranty.reload(); toast.done('보증값을 입력했습니다.'); onChanged() }, (e: Error) => setError(e.message))
  }

  const assumed = j.is_assumed || Boolean(product.data?.comparison_values_assumed)
  const source = j.result === 'WARRANTY_TO_FILL' ? p.sub
    : j.product_code ? `${j.product_code} · 제품표${product.data?.source_doc ? ` (${product.data.source_doc})` : ''}` : '—'
  const basis: [string, React.ReactNode][] = []
  if (rule) basis.push(['비교 방향', <>{rule.name_ko ?? itemName(j)}: 제품값이 {DIRECTION_NAMES[rule.direction] ?? rule.direction}{' '}
    <a className="rl" href={href(`/rules?q=${encodeURIComponent(j.item_key ?? '')}`)}>판정 규칙 보기<span className="ms" aria-hidden="true" style={{ fontSize: 14, verticalAlign: -2 }}>arrow_forward</span></a></>])
  basis.push(['적용 규칙', j.reason_text ?? '—'], ['비교', compareText(j, w)])
  if (j.locations.length > 1) basis.push(['같은 요구', `${j.locations.length}곳에서 같은 요구 (${reqText(j)})`])
  basis.push(['제품값 출처', <>{source}{assumed && <span className="st c-ora" style={{ marginLeft: 6 }} title="제품 자료에 값이 없어 팀이 정한 비교값입니다">팀 가정</span>}</>])
  if (j.type_name) basis.push(['유형', j.type_name])
  if (check) basis.push(['공학 검산', `${CHECK_NAMES[check.result]} · ${checkLine(check)}`])

  const confirm = () => {
    setBusy(true)
    setError(null)
    api.act(runId, { target: 'judgment', target_id: j.judgment_id, action: 'CONFIRM', actor_id: user!.user_id })
      .then(() => { toast.done('판정을 제안대로 확정했습니다.'); onConfirmed() }, (e: Error) => setError(e.message))
      .finally(() => setBusy(false))
  }
  // 질의 보냄 표시·되돌리기 (add-query-sent). 판정 결과는 바뀌지 않는다
  const querySent = (sent: boolean) => {
    setBusy(true)
    setError(null)
    api.act(runId, { target: 'judgment', target_id: j.judgment_id, action: sent ? 'QUERY_SENT' : 'QUERY_UNSENT', actor_id: user!.user_id })
      .then(() => { toast.done(sent ? '질의 보냄으로 표시했습니다.' : '질의 보냄 표시를 되돌렸습니다.'); onChanged() }, (e: Error) => setError(e.message))
      .finally(() => setBusy(false))
  }
  const found = req.data ? ({ AI: 'AI 추출', OCR: 'OCR 추출 · 사람 확인 필요' } as Record<string, string>)[req.data.extracted_by] ?? '규칙 추출' : null
  const confidence = req.data?.confidence != null ? `신뢰도 ${Number(req.data.confidence).toFixed(2)}` : null

  return (
    <div className="mdo">
      <div className="mdw" role="region" aria-labelledby="mdTitle">
        <div className="mdh">
          <span className={`st ${RESULT_TONES[j.result]}`}>{RESULT_NAMES[j.result]}</span>
          {j.revised && <span className="st c-blue" title="문서 추가로 다시 판정한 결과">{j.revised === 'CHANGED' ? '바뀜(개정)' : '추가(개정)'}</span>}
          <h1 id="mdTitle" className="jv-h">{itemName(j)}{j.item_name_raw && j.item_name && <span className="mden">{j.item_name_raw}</span>}</h1>
          <span className="mdpos">판정 {pos} / {total}</span>
          <button type="button" className="ib" onClick={onPrev ?? undefined} disabled={!onPrev} aria-label="이전 판정" title="이전 판정 (↑)"><span className="ms" aria-hidden="true">keyboard_arrow_up</span></button>
          <button type="button" className="ib" onClick={onNext ?? undefined} disabled={!onNext} aria-label="다음 판정" title="다음 판정 (↓)"><span className="ms" aria-hidden="true">keyboard_arrow_down</span></button>
        </div>
        <div className="mdb">
          <section className="mdl" aria-label="RFP 원문">
            <div className="mdl-top">
              <span className="ms" aria-hidden="true" style={{ fontSize: 'var(--ic-s)', color: 'var(--c-muted)' }}>description</span>
              <b className="ell">{doc?.file_name ?? req.data?.file_name ?? `파일 ${loc?.file_no ?? ''}`}</b>
              {doc && <span className="lang">{LANGS[doc.language] ?? doc.language}</span>}
            </div>
            {j.locations.length > 1 && (
              <div className="occ" role="tablist" aria-label="같은 요구가 나온 위치">
                {j.locations.map((l, i) => (
                  <button key={i} type="button" role="tab" aria-selected={i === occ} className={i === occ ? 'oc on' : 'oc'} onClick={() => setOcc(i)}>
                    {l.table_name ? `${l.table_name}${l.item_no ? ` No. ${l.item_no}` : ''} · ${l.line_start ?? ''}행` : `본문 ${l.line_start ?? ''}행`}</button>
                ))}
              </div>
            )}
            <div className="paper">
              {loc && <div className="sect">{locationText(loc)}{loc.section_title ? ` · ${loc.section_title}` : ''}</div>}
              {loc?.table_name
                ? <TableRow j={j} warranted={w ? p.val : null} />
                : loc && <SourceLines runId={runId} loc={loc} needle={j.req_value_raw} />}
            </div>
          </section>

          <section className="mdr" aria-label="판정 근거">
            <div className="lbl">비교</div>
            <div className="cmp">
              <div><span className="cl">요구값 (원문)</span><b>{reqText(j)}</b><span className="cs">{loc ? locationText(loc) : ''}</span></div>
              <div className="op" aria-hidden="true">{(rule && OPS[rule.direction]) ?? '·'}</div>
              <div><span className="cl">{j.result === 'WARRANTY_TO_FILL' ? '보증값' : '제품값'}</span><b className={j.result === 'DEVIATION_CANDIDATE' ? 'c-red' : p.cls}>{p.val}</b><span className="cs">{p.sub}</span></div>
            </div>

            <div className="lbl">판정 근거</div>
            <dl className="basis">
              {basis.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}
            </dl>
            {check && <CheckCalc key={check.check_id} check={check} />}
            <TypeFix runId={runId} requirementId={j.requirement_id} current={j.type_code ?? null} />

            <div className="lbl">판정 출처</div>
            <table className="pv"><tbody>
              <tr><th>시스템 제안</th><td><span className={`st ${RESULT_TONES[sug]}`}>{RESULT_NAMES[sug]}</span><span className="pvs">규칙 기반</span></td></tr>
              <tr><th>찾은 방법</th><td>{found ?? '—'}{confidence && <span className="pvs">{confidence}</span>}
                {req.data?.is_assumed && <span className="st c-ora" style={{ marginLeft: 6 }}>팀 가정</span>}</td></tr>
              <tr><th>담당자 확정</th><td>{conf
                ? <><span className={`st ${RESULT_TONES[j.result]}`}>{RESULT_NAMES[j.result]}</span><span className="pvs">{conf.actor} · {stamp(conf.acted_at)}</span></>
                : <span className="pend" title="확정하지 않으면 시스템 제안 그대로 상신됩니다">아직 확정 안 함</span>}</td></tr>
              <PastDecisionRow j={j} />
            </tbody></table>

            {isQuery && (
              <div className="jv-qs" style={{ marginTop: 'var(--s-4)', display: 'flex', alignItems: 'center', gap: 'var(--s-2)', flexWrap: 'wrap' }}>
                <span className="tag" title={j.query_sent_at ? `${j.query_sent_by_name ?? ''} · ${stamp(j.query_sent_at)}` : '고객에게 아직 보내지 않은 질의'}>
                  {j.query_sent_at ? `질의 보냄 · ${dueText(isoDay(new Date(j.query_sent_at)))}` : '질의 초안'}</span>
                {j.review_status !== 'REJECTED' && (j.query_sent_at
                  ? <Button onClick={() => querySent(false)} busy={busy} disabledReason={lock}>되돌리기</Button>
                  : <Button icon="outgoing_mail" onClick={() => querySent(true)} busy={busy} disabledReason={lock}>질의 보냄 표시</Button>)}
              </div>
            )}
            {j.result === 'WARRANTY_TO_FILL' && (
              <div style={{ marginTop: 'var(--s-4)' }}>
                <div className="lbl">보증값</div>
                <div><b className={p.cls}>{p.val}</b> <span className="en" style={{ display: 'inline', marginLeft: 6 }}>{p.sub}</span></div>
                {w && !w.candidate_value && !lock && (
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', margin: '6px 0' }}>
                    <label className="sr" htmlFor="mdwval">보증값</label>
                    <input className="fi" id="mdwval" value={wVal} onChange={(e) => setWVal(e.target.value)} placeholder='근거 있는 값만 입력 ("Comply"는 입력할 수 없음)' style={{ flex: '1 1 160px' }} />
                    <input className="fi" aria-label="보증값 근거" value={wWhy} onChange={(e) => setWWhy(e.target.value)} placeholder="근거 (이력에 남음)" style={{ flex: '1 1 140px' }} />
                    <Button onClick={saveW} disabledReason={!wVal.trim() || !wWhy.trim() ? '보증값과 근거를 넣어 주세요' : undefined}>입력</Button>
                  </div>
                )}
                <a className="lnk" href={href(`/reviews/${runId}/datasheet`)}>데이터시트에서 입력</a>
              </div>
            )}
            {draft && <div style={{ marginTop: 18 }}><OutputEditor key={`${draft.item_id}-${draft.text_draft}-${draft.status}`} runId={runId} item={draft} id="mdDraft"
              canEdit={!lock} onDone={() => { outputs.reload(); onChanged() }} onSaved={(m) => toast.done(m)} /></div>}
          </section>
        </div>
        <div className="mdf">
          <span className="mdf-n">↑↓ 이전·다음 판정 · Esc 목록으로</span>
          {error && <span className="c-red" role="alert">{error}</span>}
          <Button onClick={() => setEditing(true)} disabledReason={lock}>판정 변경</Button>
          <Button kind="primary" onClick={confirm} busy={busy} disabledReason={lock ?? (conf ? '이미 확정한 판정입니다' : null)}>{conf ? '확정함' : '제안대로 확정'}</Button>
        </div>
      </div>
      {editing && <EditDialog runId={runId} j={j} onClose={() => setEditing(false)}
        onDone={(was, now) => { setEditing(false); toast.done(`판정을 바꿨습니다: ${RESULT_NAMES[was]} → ${RESULT_NAMES[now]}`); onChanged() }} />}
    </div>
  )
}

/** 표 위치: 표 한 줄 (No. · Description · Unit · Employer's Req. · Warranted) */
function TableRow({ j, warranted }: { j: Judgment; warranted: string | null }) {
  const no = j.locations[0]?.item_no ?? ''
  return (
    <table className="ptab">
      <thead><tr><th>No.</th><th>Description</th><th>Unit</th><th>Employer's Req.</th><th>Warranted</th></tr></thead>
      <tbody><tr className="hitr"><td>{no}</td><td>{j.item_name_raw}</td><td>{j.unit_raw}</td><td><mark>{j.req_value_raw}</mark></td><td>{warranted ?? ''}</td></tr></tbody>
    </table>
  )
}

/** 본문 위치: 그 줄과 앞뒤 2줄. 그 줄을 강조하고 요구값에 표시 */
function SourceLines({ runId, loc, needle }: { runId: number; loc: Location; needle: string | null }) {
  const start = loc.line_start ?? 1
  const end = loc.line_end ?? start
  const from = Math.max(1, start - AROUND)
  const to = Math.min(from + MAX_LINES - 1, end + AROUND)
  const lines = useLoad(() => api.documentLines(runId, loc.file_no, from, to), [runId, loc.file_no, from, to])
  if (lines.error) return <ErrorBox error={lines.error} onRetry={lines.reload} />
  if (!lines.data) return <Loading label="원문 불러오는 중" />
  return (
    <>
      {lines.data.lines.map((l) => {
        const hit = l.line_no >= start && l.line_no <= end
        const [a, m, b] = hit ? markSplit(l.text, needle) : [l.text, '', '']
        return <div key={l.line_no} className={hit ? 'pl hitl' : 'pl'}><span className="lno">{l.line_no}</span><span className="ltx">{a}{m && <mark>{m}</mark>}{b}</span></div>
      })}
      {lines.data.partial && <p className="en" role="note">원문 파일이 없어 추출된 문장만 표시합니다.</p>}
    </>
  )
}

/** 판정 바꾸기 창: 새 판정 5종, 사유 필수 */
function EditDialog({ runId, j, onClose, onDone }: { runId: number; j: Judgment; onClose: () => void; onDone: (was: string, now: string) => void }) {
  const { user } = useSession()
  const [k, setK] = useState(j.result)
  const [why, setWhy] = useState('')
  const [hint, setHint] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const apply = () => {
    if (!why.trim()) { setHint('판정을 바꾸려면 사유를 적어 주세요.'); return }
    setBusy(true)
    setHint(null)
    api.act(runId, { target: 'judgment', target_id: j.judgment_id, action: 'EDIT', value: { result: k }, reason: why.trim(), actor_id: user!.user_id })
      .then(() => onDone(j.result, k), (e: Error) => setHint(e.message))
      .finally(() => setBusy(false))
  }
  return (
    <Modal title="판정 변경" onClose={onClose} footer={<>
      <Button onClick={onClose}>닫기</Button>
      <Button kind="primary" onClick={apply} busy={busy} disabledReason={k === j.result ? '지금 판정과 같습니다' : null}>{busy ? '적용 중…' : '적용'}</Button>
    </>}>
      <label className="lbl" htmlFor="jvNew" style={{ display: 'block' }}>새 판정</label>
      <select className="fi" id="jvNew" value={k} onChange={(e) => setK(e.target.value as Judgment['result'])}>
        {RESULT_ORDER.map((r) => <option key={r} value={r}>{RESULT_NAMES[r]}</option>)}
      </select>
      <label className="lbl" htmlFor="jvWhy" style={{ display: 'block', marginTop: 'var(--s-3)' }}>바꾸는 사유</label>
      <textarea className="ta" id="jvWhy" value={why} maxLength={500} onChange={(e) => { setWhy(e.target.value); setHint(null) }} placeholder="사유 (이력에 남음)" />
      {hint && <p className="c-red" role="alert">{hint}</p>}
      {busy && <p className="en">판정을 바꾸고 일탈·질의 목록을 다시 만드는 중입니다…</p>}
    </Modal>
  )
}
