import { useState } from 'react'
import { api, type AnswerKey, type EvalMetric, type EvalScore } from '../api'
import { Pager } from '../components/Pager'
import { stamp } from '../components/format'
import { useLoad } from '../components/useLoad'
import { usePageCss } from '../shell/pageCss'
import { href } from '../shell/router'
import { useSession } from '../shell/useSession'
import { useToast } from '../ui'

// SCR-19 정답지·채점 (목업 v4.57 Eval, add-evaluation). docs/screens/SCR-19-정답지채점.md
// 사람이 확정·수정한 판정과 유형 정답지로 지표를 코드로 잰다(CR-01). 사전·규칙을 고친 뒤 다시 채점해 개선 전후를 남긴다.
// 정답지는 명령 `rfp-db load-answer-key`로 넣는다. Claude 초안 정답지는 항상 "사람 확인 전"을 붙인다.
// 요구사항 정답지(add-requirement-answer-key)를 고르면 K1·K2·K3·K10도 잰다. 코드가 만든 정답지는 "코드 자동 · 사람 확인 전".

type Tab = 'k' | 'g' | 'l'
const TABS: [Tab, string][] = [['k', '채점 결과'], ['g', '정답지'], ['l', '개선 기록']]

const shown = (m: EvalMetric | undefined) =>
  !m || m.value === null ? '—' : m.unit === '%' ? `${m.value} %` : `${m.value} ${m.unit}`
const goal = (m: EvalMetric) =>
  m.target === null ? '—' : `${m.better === 'up' ? '≥' : m.target === 0 ? '=' : '≤'} ${m.target}${m.unit === '%' ? ' %' : ` ${m.unit}`}`
const metricOf = (s: EvalScore | undefined, code: string) => s?.metrics.items.find((m) => m.code === code)

/** 지난 기록과 비교: 좋아짐 up / 나빠짐 down / 같음 same / 비교 못 함 null */
function change(now: EvalMetric, before: EvalMetric | undefined) {
  if (!before || now.value === null || before.value === null) return null
  const d = +(now.value - before.value).toFixed(1)
  const cls = d === 0 ? 'same' : (now.better === 'up') === d > 0 ? 'up' : 'down'
  return { d, cls }
}

const REQ_CODES = ['K1', 'K2', 'K3', 'K10']

function DraftTag({ k }: { k: Pick<AnswerKey, 'made_by'> | { made_by: string | null } }) {
  if (k.made_by === 'CLAUDE_DRAFT') return <span className="st c-ora" style={{ marginLeft: 6 }}>AI 초안 · 검수 전</span>
  if (k.made_by === 'AUTO') return <span className="st c-ora" style={{ marginLeft: 6 }}>자동 생성 · 검수 전</span>
  return null
}

export function Eval() {
  usePageCss('Eval')
  const { user } = useSession()
  const [tab, setTab] = useState<Tab>('k')
  const runs = useLoad(() => api.evalRuns(), [])
  const keys = useLoad(() => api.evalKeys(), [])
  const scores = useLoad(() => api.evalScores(), [])
  const [pick, setPick] = useState<Record<number, boolean>>({})     // 넣기를 바꾼 검토 (처음: 판정 줄이 있는 검토만)
  const [keyId, setKeyId] = useState<number | null | undefined>(undefined)   // undefined = 아직 고르지 않음(첫 정답지)
  const [reqKeyId, setReqKeyId] = useState<number | null>(null)      // 요구사항 정답지 (처음엔 고르지 않음)
  const [note, setNote] = useState('')
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')
  const toast = useToast()
  const [page, setPage] = useState(1)
  const [size, setSize] = useState(10)

  const runList = runs.data ?? []
  const keyList = (keys.data ?? []).filter((k) => k.key_kind === 'TYPE')
  const reqKeys = (keys.data ?? []).filter((k) => k.key_kind === 'REQ')
  const history = scores.data ?? []
  const chosenKey = keyId === undefined ? (keyList[0]?.key_id ?? null) : keyId
  const key = keyList.find((k) => k.key_id === chosenKey)
  const isOn = (r: { run_id: number; reviewed: number }) => pick[r.run_id] ?? r.reviewed > 0
  const picked = runList.filter(isOn)
  // 검토 고르기 (update-eval-run-pick): 검색은 화면에서 거르고, 모두 고르기·해제는 보이는 줄에만
  const [q, setQ] = useState('')
  const needle = q.trim().toLowerCase()
  const shownRuns = needle ? runList.filter((r) => `${r.review_no} ${r.review_name ?? ''}`.toLowerCase().includes(needle)) : runList
  const pickShown = (on: boolean) => setPick({ ...pick, ...Object.fromEntries(shownRuns.map((r) => [r.run_id, on])) })
  const [latest, previous] = history

  const rows = latest ? latest.metrics.items.map((m) => ({ m, before: metricOf(previous, m.code) })) : []
  const measured = rows.filter((r) => r.m.passed !== null)
  const better = rows.filter((r) => change(r.m, r.before)?.cls === 'up').length

  const run = () => {
    setRunning(true)
    setError('')
    api.score(picked.map((r) => r.run_id), chosenKey, note, user?.user_id ?? null, reqKeyId)
      .then((s) => {
        setNote('')
        setTab('k')
        setPage(1)
        scores.reload()
        toast.done(`채점을 마쳤습니다. 검토 ${s.run_ids.length}건${s.key_name ? `, 정답지 "${s.key_name}"` : ''}${s.req_key_name ? `, 요구사항 정답지 "${s.req_key_name}"` : ''} 기준으로 지표 ${s.metrics.items.length}개를 쟀습니다.`)
      }, (e: Error) => setError(e.message))
      .finally(() => setRunning(false))
  }

  return (
    <main className="main">
      <div className="ttl"><div><h1>정답지·채점</h1><p className="tb-sub">사람이 확정한 판정을 정답지로 삼아, 사전·규칙·제품표를 고칠 때마다 점수를 다시 잽니다.</p></div>
        <button type="button" className="bp" onClick={run} disabled={running || picked.length === 0}
          title={picked.length === 0 ? '정답지 탭에서 채점할 검토를 고르세요' : undefined}>
          <span className="ms" aria-hidden="true" style={{ fontSize: 'var(--ic-s)' }}>play_arrow</span>{running ? '채점 중…' : '지금 채점하기'}</button></div>
      <div className="sh-note"><span className="ms" aria-hidden="true">info</span><span>점수는 시스템이 자동으로 계산합니다. 판정 정확도(K5·K6)는 엔지니어가 <b>확정·수정한 줄</b>을 정답으로 보고, 유형 분류 정확도(K13)는 고른 유형 정답지로, 추출 재현율·정확도(K1·K2)·값(K3)·위험 조건 재현율(K10)은 고른 요구사항 정답지로 잽니다. 지난 검토의 사람 판정은 새 검토의 판정을 자동으로 바꾸지 않으며, 사람 검토를 건너뛰는 자동 확정은 하지 않습니다.</span></div>
      {error && <div className="sh-note c-red" role="alert"><span className="ms" aria-hidden="true">error</span><span>{error}</span></div>}
      <div className="sh-sum">
        <span>정답지<b>{key ? `${key.rows.toLocaleString('en-US')}건` : '없음'}</b></span><span>검토<b>{picked.length}건</b></span>
        <span>마지막 채점<b>{latest ? stamp(latest.scored_at) : '—'}</b></span>
        <span>목표 달성<b className="c-green">{latest ? `${measured.filter((r) => r.m.passed).length} / ${measured.length}` : '—'}</b></span>
        <span>지난번보다 좋아짐<b className="c-blue">{previous ? better : '—'}</b></span>
      </div>
      <div className="pgtabs" role="tablist" style={{ marginTop: 24 }}>
        {TABS.map(([k, label]) => <button key={k} type="button" role="tab" className={tab === k ? 'on' : ''} aria-selected={tab === k} onClick={() => setTab(k)}>{label}</button>)}
      </div>
      {tab === 'k' && (
        <div className="sh-box">
          <div className="ev-tr sh-th"><span>지표</span><span>무엇을 재나</span><span>지난{previous ? ` (${stamp(previous.scored_at).slice(0, 5)})` : ''}</span><span>이번{latest ? ` (${stamp(latest.scored_at).slice(0, 5)})` : ''}</span><span>변화</span><span>목표</span></div>
          {scores.error && <div className="ev-row c-red" style={{ padding: '11px 16px' }}>{scores.error}</div>}
          {scores.data && !latest && <div className="ev-row sh-mut" style={{ padding: '11px 16px' }}>아직 채점 기록이 없습니다. 정답지 탭에서 검토와 정답지를 고르고 [지금 채점하기]를 누르세요.</div>}
          {rows.slice((page - 1) * size, page * size).map(({ m, before }) => {
            const c = change(m, before)
            return (
              <div key={m.code} className="ev-tr ev-row" data-code={m.code}>
                <span>{m.code !== 'TIME' && <b className="mono">{m.code} </b>}{m.name}{m.code === 'K13' && <DraftTag k={{ made_by: latest?.key_made_by ?? null }} />}{REQ_CODES.includes(m.code) && <DraftTag k={{ made_by: latest?.req_key_made_by ?? null }} />}</span>
                <span className="sh-mut">{m.measure}{m.note && <span style={{ display: 'block' }}>{m.note}</span>}</span>
                <span className="mono sh-mut">{shown(before)}</span>
                <span className="mono" style={{ fontWeight: 600 }}>{shown(m)}{m.num !== null && m.den !== null && <span className="sh-mut" style={{ display: 'block', fontWeight: 400 }}>{m.num} / {m.den}</span>}</span>
                <span className={c?.cls}>{c === null ? '—' : c.d === 0 ? '변화 없음' : (c.d > 0 ? '▲ ' : '▼ ') + Math.abs(c.d)}</span>
                <span>{m.passed === null ? <span className="st c-grey">{goal(m)}</span> : <span className={m.passed ? 'st c-green' : 'st c-ora'}>{goal(m)}</span>}</span>
              </div>
            )
          })}
          {latest && page * size >= rows.length && latest.metrics.not_measured.map((m) => (
            <div key={m.code} className="ev-tr ev-row sh-mut"><span><b className="mono">{m.code}</b> {m.name}</span><span>{m.note}</span><span>—</span><span>재지 않음</span><span>—</span><span /></div>
          ))}
        </div>
      )}
      {tab === 'k' && rows.length > 0 && <Pager total={rows.length} page={page} size={size} shown={rows.slice((page - 1) * size, page * size).length} onPage={setPage} onSize={(n) => { setSize(n); setPage(1) }} />}
      {tab === 'g' && (
        <>
          <div className="ev-pick" role="group" aria-label="채점할 검토 고르기">
            <input className="fi" type="search" value={q} onChange={(e) => setQ(e.target.value)} aria-label="검토 찾기"
              placeholder="검토 번호·이름" style={{ width: 220 }} />
            <button type="button" className="bo" onClick={() => pickShown(true)} disabled={shownRuns.length === 0}>모두 고르기</button>
            <button type="button" className="bo" onClick={() => pickShown(false)} disabled={shownRuns.length === 0}>모두 해제</button>
            <span className="ev-picked" data-testid="eval-picked">검토 <b>{picked.length}건</b> 고름{needle && <span className="sh-mut"> · 보이는 검토 {shownRuns.length}건</span>}</span>
          </div>
          <div className="sh-box">
            <div className="gt-tr sh-th"><span>넣기</span><span>검토</span><span>확정한 사람</span><span>마지막 확정</span><span>판정 줄</span></div>
            {runs.error && <div className="ev-row c-red" style={{ padding: '11px 16px' }}>{runs.error}</div>}
            {runs.data && runList.length === 0 && <div className="ev-row sh-mut" style={{ padding: '11px 16px' }}>분석을 마친 검토가 없습니다. 검토 상세 판정 탭에서 판정을 확정하면 판정 정확도(K5)를 잴 수 있습니다.</div>}
            {runs.data && runList.length > 0 && shownRuns.length === 0 && <div className="ev-row sh-mut" style={{ padding: '11px 16px' }}>찾는 검토가 없습니다.</div>}
            {shownRuns.map((r) => (
              <label key={r.run_id} className="gt-tr ev-row"><input type="checkbox" checked={isOn(r)} onChange={() => setPick({ ...pick, [r.run_id]: !isOn(r) })} />
                <span><b>{r.review_name ?? r.review_no}</b><a className="mono sh-mut" style={{ display: 'block' }} href={href(`/reviews/${r.run_id}`)} onClick={(e) => e.stopPropagation()}>{r.review_no}</a></span>
                <span className="sh-mut">{r.reviewer ?? '—'}</span>
                <span className="mono sh-mut">{r.last_reviewed_at ? stamp(r.last_reviewed_at) : '—'}</span><span className="mono">{r.reviewed}건{r.reviewed === 0 && <span className="sh-mut" style={{ display: 'block', fontFamily: 'inherit' }}>요구사항 정답지용</span>}</span></label>
            ))}
          </div>
          <h3 style={{ margin: '24px 0 8px' }}>유형 정답지</h3>
          <div className="sh-box">
            <div className="gt-tr sh-th"><span>고름</span><span>정답지</span><span>사람 확인</span><span>넣은 날</span><span>줄</span></div>
            <label className="gt-tr ev-row"><input type="radio" name="answer-key" checked={chosenKey === null} onChange={() => setKeyId(null)} />
              <span><b>유형 정답지 없이</b><span className="sh-mut" style={{ display: 'block' }}>K13을 재지 않습니다</span></span><span /><span /><span /></label>
            {keyList.map((k) => (
              <label key={k.key_id} className="gt-tr ev-row"><input type="radio" name="answer-key" checked={chosenKey === k.key_id} onChange={() => setKeyId(k.key_id)} />
                <span><b>{k.key_name}</b><DraftTag k={k} />{k.ambiguous > 0 && <span className="sh-mut" style={{ display: 'block' }}>애매한 줄 {k.ambiguous}개는 따로 셉니다</span>}</span>
                <span className="mono sh-mut">{k.human_checked} / {k.rows}</span>
                <span className="mono sh-mut">{stamp(k.created_at)}</span><span className="mono">{k.rows}건</span></label>
            ))}
          </div>
          <h3 style={{ margin: '24px 0 8px' }}>요구사항 정답지</h3>
          <div className="sh-box">
            <div className="gt-tr sh-th"><span>고름</span><span>정답지</span><span>대상 문서</span><span>넣은 날</span><span>줄</span></div>
            <label className="gt-tr ev-row"><input type="radio" name="req-key" checked={reqKeyId === null} onChange={() => setReqKeyId(null)} />
              <span><b>요구사항 정답지 없이</b><span className="sh-mut" style={{ display: 'block' }}>K1·K2·K3·K10을 재지 않습니다</span></span><span /><span /><span /></label>
            {reqKeys.map((k) => (
              <label key={k.key_id} className="gt-tr ev-row" data-key={k.key_name}><input type="radio" name="req-key" checked={reqKeyId === k.key_id} onChange={() => setReqKeyId(k.key_id)} />
                <span><b>{k.key_name}</b><DraftTag k={k} /></span>
                <span className="sh-mut">{k.doc_name ?? '검토의 모든 문서'}</span>
                <span className="mono sh-mut">{stamp(k.created_at)}</span><span className="mono">{k.rows}건</span></label>
            ))}
          </div>
          <label className="sh-note" style={{ display: 'flex', gap: 8, alignItems: 'center' }}><span className="ms" aria-hidden="true">edit_note</span>
            <span style={{ whiteSpace: 'nowrap' }}>무엇을 고쳤나</span>
            <input type="text" value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} placeholder="예: 비교 방향 규칙 3건 수정 (채점 기록에 남습니다)" style={{ flex: 1 }} aria-label="무엇을 고쳤나" /></label>
          <div className="sh-note"><span className="ms" aria-hidden="true">upload_file</span><span>정답지 등록은 시스템 담당자에게 요청하세요. AI 초안·자동 생성 정답지는 담당자가 검수한 항목만 검수 완료로 셉니다.</span></div>
        </>
      )}
      {tab === 'l' && (
        <div className="sh-box">
          <div className="lg-tr sh-th"><span>날짜</span><span>정답지</span><span>무엇을 고쳤나</span><span>점수 (K5 · K13)</span><span>한 사람</span></div>
          {scores.data && history.length === 0 && <div className="ev-row sh-mut" style={{ padding: '11px 16px' }}>채점 기록이 없습니다.</div>}
          {history.map((s) => (
            <div key={s.score_id} className="lg-tr ev-row"><span className="mono sh-mut">{stamp(s.scored_at)}</span>
              <span>{s.key_name && <span className="st c-grey">{s.key_name}</span>}{s.req_key_name && <span className="st c-grey">{s.req_key_name}</span>}{!s.key_name && !s.req_key_name && <span className="sh-mut">판정만</span>}</span>
              <span>{s.note ?? <span className="sh-mut">메모 없음</span>}<span className="sh-mut" style={{ display: 'block' }}>검토 {s.run_ids.length}건 · 시스템 버전 {s.code_version ?? '—'}</span></span>
              <span className="mono c-blue" style={{ fontWeight: 600 }}>{shown(metricOf(s, 'K5'))} · {shown(metricOf(s, 'K13'))}</span>
              <span className="sh-mut">{s.scored_by_name ?? '—'}</span></div>
          ))}
        </div>
      )}
    </main>
  )
}
