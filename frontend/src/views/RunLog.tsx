import { useState, type ReactNode } from 'react'
import { api, type AiCall, type AiCalls, type AiUsageRow, type RunFlow, type RunLogItem } from '../api'
import { AiModeLine } from '../components/AiMode'
import './detail.css'
import { stamp } from '../components/format'
import { FLOW_ACTION_NAMES, FLOW_COUNT_NAMES, STAGE_NAMES, STAGE_TONES, STEP_NAMES } from '../components/labels'
import { duration } from '../components/progress'
import { useLoad } from '../components/useLoad'
import { href, navigate } from '../shell/router'
import { usePageCss } from '../shell/pageCss'

// SCR-25 실행 기록 (목업에 없음, add-run-log, NFR-09). docs/screens/SCR-25_공유.md
// 검토마다 걸린 시간·단계별 시간·AI 사용량·추정 비용. 비용은 모델 단가(팀 가정)로 어림한 값 (CR-06).

const num = (n: number) => n.toLocaleString('en-US')
// 1분 안쪽은 소수 한 자리 초 (규칙만 쓴 실행은 1초도 안 걸린다)
const secs = (s: number | null) => (s === null ? '—' : s < 60 ? `${s.toFixed(1)}초` : duration(s * 1000))
const won = (n: number | null) => (n === null ? '단가 없음' : `${num(n)}원`)
const tokens = (r: RunLogItem) => r.llm_input_tokens + r.llm_output_tokens + r.llm_thinking_tokens
/** 이 기능 전에 처리한 실행: 단계 시간도 AI 기록도 없다 */
const noLog = (r: RunLogItem) => r.steps.length === 0

const ROLE_NAMES: Record<string, string> = {
  classify: '문서 분류', label: '문장 구분', type: '유형', risk: '위험 설명',
  verify: '검증', draft: '문장 초안', handoff: '협조 질문', assistant: '검토 도우미',
}

const RESULT_NAMES: Record<AiCall['result'], string> = {
  OK: '성공', FORMAT_ERROR: '형식 오류', CONFIG_ERROR: '설정 오류', TIMEOUT: '시간 초과', CONNECTION_ERROR: '연결 오류',
}

/** 처리 단계에 들지 않는 AI 호출(협조 요청 메일·검토 도우미 등)은 단계 이름이 없다 */
const OUTSIDE = '분석 밖 (협조 요청·도우미 등)'
const stepName = (s: string | null) => (s ? STEP_NAMES[s] ?? s : OUTSIDE)
const roleName = (r: string | null) => (r ? ROLE_NAMES[r] ?? r : '—')

/** 프롬프트 판 (add-prompt-eval): 역할별 판, 예전 실행은 전체 판 하나 */
function Prompts({ r }: { r: RunLogItem }) {
  if (!r.llm_model) return <p className="dimv">AI를 쓰지 않은 실행입니다.</p>
  const roles = r.prompt_versions ? Object.entries(r.prompt_versions) : []
  if (!roles.length && !r.prompt_version) return <p className="dimv">기록 없음</p>
  if (!roles.length) return <p className="en">전체 {r.prompt_version} (역할별 판 도입 전)</p>
  return (
    <table className="mini rlprompt"><thead><tr><th>AI 역할</th><th>판</th></tr></thead>
      <tbody>{roles.map(([role, v]) => <tr key={role}><td>{ROLE_NAMES[role] ?? role}</td><td className="mono">{v}</td></tr>)}</tbody></table>
  )
}

/** 설명은 ⓘ에 마우스를 올리면 (Fiori: 필요할 때 자세히) */
function Info({ text }: { text: string }) {
  return <span className="rlinfo ms" role="img" aria-label={text} title={text}>info</span>
}

const DAYS = [7, 30, 90] as const

/** AI 사용량 (update-run-log-ai-usage): 분석과 분석 밖 AI 호출을 날짜·기능별로. 합계는 응답 값 (CR-01), 비용은 팀 가정 (CR-06) */
function AiUsageBox() {
  const [days, setDays] = useState<number>(30)
  const [feature, setFeature] = useState<string | null>(null)
  const usage = useLoad(() => api.aiUsage(days), [days])
  const items = [...(usage.data?.items ?? [])].sort((a, b) => b.day.localeCompare(a.day) || a.feature.localeCompare(b.feature))
  const kinds = [...new Map(items.map((i) => [i.feature, i.feature_name])).entries()]
  const shown = feature ? items.filter((i) => i.feature === feature) : items
  const total = usage.data?.total_cost_krw
  const pick = (d: number) => { setDays(d); setFeature(null) }
  const toks = (i: AiUsageRow) => `${num(i.input_tokens)} / ${num(i.output_tokens)} / ${num(i.thinking_tokens)}`
  return (
    <section className="aiu" aria-labelledby="aiuh">
      <div className="aiu-h">
        <h2 id="aiuh">AI 사용량</h2>
        <div className="seg" role="group" aria-label="AI 사용량 기간">
          {DAYS.map((d) => <button key={d} type="button" className={days === d ? 'on' : ''} aria-pressed={days === d} onClick={() => pick(d)}>{d}일</button>)}
        </div>
        {usage.data && <p className="aiu-sum" data-testid="ai-usage-sum">
          호출 <b>{num(usage.data.total_calls)}회</b> · 추정 비용 <b>{total == null ? '단가 모름' : `${num(total)}원`}</b>
          {total != null && <span className="tag" title="모델 단가를 팀이 정한 값으로 어림했습니다 (1$ = 1,500원)">팀 가정</span>}</p>}
      </div>
      <p className="aiu-n">분석과 검토 도우미·협조 요청 확인할 점·비교 제품 바꾸기·확정 뒤 다시 쓰기처럼 분석 밖에서 부른 AI를 함께 셉니다. 실제 청구 금액은 Google 결제 화면에서 확인합니다.</p>
      {usage.error && <p className="c-red" role="alert">{usage.error} <button type="button" className="lnk" onClick={usage.reload}>다시 불러오기</button></p>}
      {!usage.data && !usage.error && <p className="dimv">불러오는 중…</p>}
      {usage.data && items.length === 0 && <p className="dimv aiu-empty">이 기간에 AI를 쓴 기록이 없습니다.</p>}
      {items.length > 0 && <>
        <div className="fbar" role="group" aria-label="AI 사용 기능">
          <button type="button" className={'chip' + (feature === null ? ' on' : '')} aria-pressed={feature === null} onClick={() => setFeature(null)}>전체 <span className="n">{items.length}</span></button>
          {kinds.map(([k, name]) => (
            <button key={k} type="button" className={'chip' + (feature === k ? ' on' : '')} aria-pressed={feature === k}
              onClick={() => setFeature(k)}>{name} <span className="n">{items.filter((i) => i.feature === k).length}</span></button>
          ))}
        </div>
        <div className="tw">
          <table className="tbl aiu-t">
            <thead><tr><th>날짜</th><th>기능</th><th>모델</th><th style={{ textAlign: 'right' }}>호출</th>
              <th style={{ textAlign: 'right' }} title="입력 / 출력 / 생각">토큰 (입력 / 출력 / 생각)</th><th style={{ textAlign: 'right' }}>추정 비용</th></tr></thead>
            <tbody>
              {shown.map((i) => (
                <tr key={`${i.day}-${i.feature}-${i.model ?? ''}`}>
                  <td>{i.day}</td><td>{i.feature_name}</td><td>{i.model ?? '—'}</td>
                  <td style={{ textAlign: 'right' }}>{num(i.calls)}{i.retries > 0 && <div className="en c-ora">재시도 {i.retries}</div>}</td>
                  <td style={{ textAlign: 'right' }}>{toks(i)}</td>
                  <td style={{ textAlign: 'right' }}>{i.estimated_cost_krw == null ? <span className="dimv">단가 모름</span> : `${num(i.estimated_cost_krw)}원`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {feature && <p className="en" style={{ marginTop: 6 }}>거른 줄 호출 {num(shown.reduce((n, i) => n + i.calls, 0))}회</p>}
      </>}
    </section>
  )
}

export function RunLog() {
  usePageCss('Products')
  const log = useLoad(() => api.runLog(), [])
  const rows = log.data ?? []
  const done = rows.filter((r) => r.seconds !== null && r.stage !== 'PROCESSING' && !noLog(r))
  const avg = done.length ? done.reduce((n, r) => n + (r.seconds ?? 0), 0) / done.length : null
  const calls = rows.reduce((n, r) => n + r.llm_calls, 0)
  const cost = rows.reduce((n, r) => n + (r.estimated_cost_krw ?? 0), 0)

  return (
    <main className="main">
      <div className="idl"><span>최근 실행 {rows.length}건</span><span>아래 표는 분석 중 AI 사용량만 집계합니다 (그 밖의 사용량은 위 AI 사용량 참고)</span><AiModeLine as="span" /></div>
      <div className="ttl"><h1>실행 기록</h1></div>
      <AiUsageBox />
      <div className="kpis">
        <div className="kpi"><div className="l">실행</div><b>{log.data ? rows.length : '—'}</b><div className="s">기록 있는 실행 {rows.filter((r) => !noLog(r)).length}건</div></div>
        <div className="kpi"><div className="l">평균 걸린 시간</div><b>{avg === null ? '—' : secs(avg)}</b><div className="s">끝난 실행 {done.length}건</div></div>
        <div className="kpi"><div className="l">AI 요청</div><b>{num(calls)}</b><div className="s">재시도 {num(rows.reduce((n, r) => n + r.llm_retries, 0))}번 포함</div></div>
        <div className="kpi"><div className="l">추정 비용 합</div><b>{num(cost)}원</b><div className="s">추정 · 팀 가정 단가, 1$ = 1,500원</div></div>
      </div>
      <div className="tw" style={{ marginTop: 16 }}>
        <table className="tbl rltbl">
          <thead><tr>
            <th>검토</th><th>상태</th><th>시작</th><th style={{ textAlign: 'right' }}>걸린 시간</th><th>모델</th>
            <th style={{ textAlign: 'right' }}>AI 요청</th><th style={{ textAlign: 'right' }}>토큰</th><th style={{ textAlign: 'right' }}>추정 비용</th>
            <th style={{ textAlign: 'right' }}>문서</th><th style={{ textAlign: 'right' }}>요구사항</th><th style={{ textAlign: 'right' }}>판정</th><th style={{ textAlign: 'right' }}>다시 시도</th>
          </tr></thead>
          <tbody>
            {log.data === null && !log.error && <tr><td colSpan={12} className="dimv">불러오는 중…</td></tr>}
            {log.error && <tr><td colSpan={12} className="c-red">{log.error}</td></tr>}
            {rows.map((r) => (
                <tr key={r.run_id} style={{ cursor: 'pointer' }} tabIndex={0} title="실행 기록 상세 보기"
                  onClick={() => navigate(`/runlog/${r.run_id}`)}
                  onKeyDown={(e) => { if (e.key === 'Enter') navigate(`/runlog/${r.run_id}`) }}>
                  <td><a href={href(`/reviews/${r.run_id}`)} onClick={(e) => e.stopPropagation()}>{r.review_no}</a>
                    <div className="en">{r.review_name ?? r.project_name ?? ''}</div></td>
                  <td><span className={`st ${STAGE_TONES[r.stage] ?? ''}`}>{STAGE_NAMES[r.stage] ?? r.stage}</span>
                    {r.cancelled && <div className="en">취소함</div>}</td>
                  <td>{stamp(r.started_at)}</td>
                  <td style={{ textAlign: 'right' }}>{r.stage === 'PROCESSING' ? '처리 중' : secs(r.seconds)}</td>
                  <td>{r.llm_model ?? '규칙 기반'}<div className="en">사전 {r.dict_version}</div></td>
                  <td style={{ textAlign: 'right' }}>{noLog(r) ? <span className="dimv">기록 없음</span> : <>{num(r.llm_calls)}{r.llm_retries > 0 && <div className="en c-ora">재시도 {r.llm_retries}</div>}{r.explanations_dropped > 0 && <div className="en c-ora" title="원문 근거와 맞지 않아 제외한 AI 위험 설명">AI 설명 버림 {r.explanations_dropped}</div>}{r.explanations_unverified > 0 && <div className="en c-ora" title="AI 재검증에서 근거 확인이 안 된 위험 설명">검증 확인 필요 {r.explanations_unverified}</div>}{(r.type_examples ?? 0) > 0 && <div className="en" title="담당자가 고친 유형을 참고 예시로 넣어 AI에 물은 항목">유형 예시 {r.type_examples}줄</div>}</>}</td>
                  <td style={{ textAlign: 'right' }}>{noLog(r) ? '—' : num(tokens(r))}</td>
                  <td style={{ textAlign: 'right' }}>{noLog(r) ? '—' : <>{won(r.estimated_cost_krw)}{r.cost_assumed && <div className="en">추정 · 팀 가정</div>}</>}</td>
                  <td style={{ textAlign: 'right' }}>{r.documents}{r.documents_reused > 0 && <div className="en">다시 씀 {r.documents_reused}</div>}</td>
                  <td style={{ textAlign: 'right' }}>{num(r.requirements)}</td>
                  <td style={{ textAlign: 'right' }}>{num(r.judgments)}</td>
                  <td style={{ textAlign: 'right' }}>{r.retries}</td>
                </tr>
            ))}
          </tbody>
        </table>
      </div>
    </main>
  )
}

/** 실행 기록 상세 (update-runlog-detail, update-runlog-fiori): Fiori 객체 화면처럼 머리글 KPI(병목 단계)·구역 이동,
 * 단계별 처리 한 표(걸린 시간·AI 시간·바뀐 것·사람 동작), AI 호출(이름 붙은 거르기·결과 없음 안내), 접는 프롬프트 판 */
export function RunLogDetail({ runId }: { runId: number }) {
  usePageCss('Products')
  const log = useLoad(() => api.runLog(), [])
  const r = (log.data ?? []).find((x) => x.run_id === runId)
  const calls = useLoad(() => api.aiCalls(runId), [runId])
  const flow = useLoad(() => api.runFlow(runId), [runId])
  const [attempt, setAttempt] = useState<number | null>(null)
  if (log.error) return <main className="main"><p className="c-red">{log.error}</p></main>
  if (!log.data) return <main className="main"><p className="dimv">불러오는 중…</p></main>
  if (!r) return <main className="main"><Back /><p className="dimv">이 검토의 실행 기록이 없습니다.</p></main>

  const tries = [...new Set(r.steps.map((s) => s.attempt))]
  const shownTry = attempt ?? (tries.length ? Math.max(...tries) : 0)
  const steps = r.steps.filter((s) => s.attempt === shownTry)
  const total = steps.reduce((n, s) => n + (s.seconds ?? 0), 0)
  const top = steps.reduce<typeof steps[number] | null>((m, s) => (s.seconds ?? 0) > (m?.seconds ?? 0) ? s : m, null)
  const go = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })

  return (
    <main className="main">
      <Back />
      <div className="ttl"><h1>실행 기록 · {r.review_no}</h1>
        <a className="lnk" href={href(`/reviews/${r.run_id}`)}>검토 상세 보기</a></div>
      <p className="en" style={{ margin: '4px 0 0' }}>{r.review_name ?? r.project_name ?? ''}</p>
      <div className="kpis">
        <div className="kpi"><div className="l">상태</div><b><span className={`st ${STAGE_TONES[r.stage] ?? ''}`}>{STAGE_NAMES[r.stage] ?? r.stage}</span></b>
          <div className="s">시작 {stamp(r.started_at)}{r.cancelled ? ' · 취소함' : ''}</div></div>
        <div className="kpi"><div className="l">걸린 시간</div><b>{r.stage === 'PROCESSING' ? '처리 중' : secs(r.seconds)}</b>
          <div className="s">다시 시도 {r.retries}번</div></div>
        <div className="kpi rlkpi-top"><div className="l">가장 오래 걸린 단계</div>
          <b>{top && total > 0 ? stepName(top.step) : '—'}</b>
          <div className="s">{top && total > 0 ? `${secs(top.seconds)} · 전체의 ${Math.round(((top.seconds ?? 0) / total) * 100)} %` : '단계 기록 없음'}</div></div>
        <div className="kpi"><div className="l">AI 요청</div><b>{noLog(r) ? '—' : num(r.llm_calls)}</b>
          <div className="s">{r.llm_model ?? '규칙 기반'} · 토큰 {noLog(r) ? '—' : num(tokens(r))}</div></div>
        <div className="kpi"><div className="l">추정 비용</div><b>{noLog(r) ? '—' : won(r.estimated_cost_krw)}</b>
          <div className="s">{r.cost_assumed ? '추정 · 팀 가정' : `사전 ${r.dict_version}`}</div></div>
        <div className="kpi"><div className="l">문서 · 요구사항 · 판정</div><b>{r.documents} · {num(r.requirements)} · {num(r.judgments)}</b>
          <div className="s">다시 쓴 문서 {r.documents_reused}</div></div>
      </div>
      <nav className="rlnav" aria-label="구역으로 이동">
        <button type="button" onClick={() => go('rl-steps')}>단계별 처리</button>
        <button type="button" onClick={() => go('rl-calls')}>AI 호출</button>
        <button type="button" onClick={() => go('rl-prompts')}>프롬프트 판</button>
      </nav>

      <section id="rl-steps" className="rlcard rlopen" aria-labelledby="rl-steps-h">
        <div className="rlcard-h"><h2 id="rl-steps-h">단계별 처리</h2>
          {tries.length > 1 && <div className="rlseg" role="group" aria-label="처리 회차">
            {tries.map((t) => <button key={t} type="button" aria-pressed={t === shownTry} className={t === shownTry ? 'on' : ''}
              onClick={() => setAttempt(t)}>{t === 0 ? '처음 처리' : `다시 시도 ${t}`}</button>)}</div>}</div>
        {noLog(r) ? <p className="dimv">기록 없음 (기록 기능 도입 전 검토)</p>
          : <StepTable label={shownTry === 0 ? '처음 처리' : `다시 시도 ${shownTry}`} steps={steps} top={top?.step ?? null}
              aiMs={calls.data?.step_ms ?? []} flow={flow.data} flowError={flow.error} />}
      </section>

      <section id="rl-calls" className="rlcard" aria-labelledby="rl-calls-h">
        <AiCallList runId={runId} data={calls.data} error={calls.error} />
      </section>

      <section id="rl-prompts" className="rlcard" aria-labelledby="rl-prompts-h">
        <details><summary><h2 id="rl-prompts-h">프롬프트 판</h2><Info text="AI 역할마다 쓴 지시문의 판 번호입니다. 판이 다르면 같은 문서도 AI 답이 다를 수 있습니다." /><span className="en">눌러서 펼치기</span></summary>
          <Prompts r={r} /></details>
      </section>
    </main>
  )
}

function Back() {
  return <p style={{ margin: '0 0 8px' }}><a className="lnk" href={href('/runlog')}>← 실행 기록</a></p>
}

/** 단계별 처리 한 표 (Fiori: 한 사실은 한 곳에). 걸린 시간은 실행 기록 단계 시각, 바뀐 것·사람 동작·멈춘 자리는 흐름 기록 */
function StepTable({ label, steps, top, aiMs, flow, flowError }: {
  label: string; steps: RunLogItem['steps']; top: string | null; aiMs: { step: string; ms: number }[]
  flow: RunFlow | null; flowError: string | null
}) {
  const most = Math.max(1, ...steps.map((s) => s.seconds ?? 0))
  const ai = new Map(aiMs.map((x) => [x.step, x.ms]))
  const byNode = new Map((flow?.steps ?? []).map((f) => [f.node, f]))
  const known = new Set(steps.map((s) => s.step))
  const people = (flow?.steps ?? []).filter((f) => !known.has(f.node) && f.action)
  const stopText = !flow?.recorded ? '' : flow.stop === 'END' ? '흐름 끝' : flow.stop ? `${STEP_NAMES[flow.stop] ?? flow.stop}에서 멈춤`
    : flow.next_node ? `${STEP_NAMES[flow.next_node] ?? flow.next_node} 앞에서 멈춤 (처리 중이거나 실패)` : ''
  return (
    <>
      <p className="en" style={{ margin: '0 0 8px' }}>{label}</p>
      <table className="mini rlsteptbl">
        <thead><tr><th>단계</th><th>걸린 시간</th>
          <th>AI 시간 <Info text="그 단계에서 부른 AI 요청 시간의 합입니다. 여러 요청을 동시에 보내므로 걸린 시간보다 길 수 있습니다." /></th>
          <th>바뀐 것</th></tr></thead>
        <tbody>
          {steps.map((s) => {
            const f = byNode.get(s.step)
            return (
              <tr key={s.step} className={s.step === top ? 'rltop' : undefined}>
                <td>{stepName(s.step)}{s.step === top && <span className="st c-ora rltag">가장 오래 걸림</span>}</td>
                <td><span className="rltime"><span className="rlbar"><i style={{ width: `${((s.seconds ?? 0) / most) * 100}%` }} /></span>
                  <span>{s.seconds === null ? '끝나지 않음' : secs(s.seconds)}</span></span></td>
                <td>{ai.has(s.step) ? secs((ai.get(s.step) ?? 0) / 1000) : <span className="dimv">—</span>}</td>
                <td className="en">{f?.changes.length ? f.changes.map((c) => `${FLOW_COUNT_NAMES[c.key] ?? c.key} ${c.before ?? 0} → ${c.after}`).join(' · ') : '—'}</td>
              </tr>
            )
          })}
          {people.map((f, i) => (
            <tr key={`p${i}`}><td>{STEP_NAMES[f.node] ?? f.node}</td><td colSpan={2} className="dimv">사람 동작</td>
              <td><span className="rlact">{FLOW_ACTION_NAMES[f.action ?? ''] ?? f.action}</span></td></tr>
          ))}
        </tbody>
      </table>
      {flowError && <p className="c-red">{flowError}</p>}
      {flow && !flow.recorded && <p className="dimv">흐름 기록 없음 (바뀐 것과 멈춘 자리를 알 수 없음)</p>}
      {stopText && <p className="rlstop">{stopText}</p>}
    </>
  )
}

/** AI 호출 목록 (add-ai-call-trace, FR-21): 이름 붙은 거르기(단계·역할)·느린 순·초기화, 결과 없음 안내 (Fiori 거르기 막대·No Data) */
function AiCallList({ runId, data, error }: { runId: number; data: AiCalls | null; error: string | null }) {
  const [step, setStep] = useState('')
  const [role, setRole] = useState('')
  const [slow, setSlow] = useState(false)
  const head = (extra?: ReactNode) => <div className="rlcard-h"><h2 id="rl-calls-h">AI 호출</h2>{extra}</div>
  if (error) return <>{head()}<p className="c-red">{error}</p></>
  if (!data) return <>{head()}<p className="dimv">AI 호출 기록 불러오는 중…</p></>
  if (data.count === 0) return <>{head()}<p className="dimv">호출 기록 없음</p></>
  const key = (v: string | null) => v ?? ''
  const steps = [...new Set(data.calls.map((c) => key(c.step)))]
  const roles = [...new Set(data.calls.map((c) => key(c.role)))]
  const shown = data.calls.filter((c) => (!step || key(c.step) === step) && (!role || key(c.role) === role))
  const rows = slow ? [...shown].sort((a, b) => b.duration_ms - a.duration_ms) : shown
  const fails = Object.entries(data.by_result).filter(([k]) => k !== 'OK')
  const filtered = Boolean(step || role || slow)
  return (
    <>
      {head(<a className="lnk" href={api.aiCallsOtelUrl(runId)} download>OpenTelemetry로 내보내기</a>)}
      <p className="en" style={{ margin: '0 0 8px' }}>
        {num(data.count)}건 · {fails.length ? <span className="c-ora">{fails.map(([k, n]) => `${RESULT_NAMES[k as AiCall['result']] ?? k} ${n}`).join(' · ')}</span> : '모두 성공'}
        {' · '}같은 입력에 다른 답 {data.different_answers}건{' '}
        <Info text="문서 원문은 저장하지 않고, 같은 입력인지 비교할 수 있는 요약값(해시)만 저장합니다." /></p>
      <div className="rlfilter" role="group" aria-label="AI 호출 거르기">
        <label>단계<select className="fi" aria-label="단계 거르기" value={step} onChange={(e) => setStep(e.target.value)}>
          <option value="">모든 단계</option>
          {steps.map((s) => <option key={s} value={s}>{stepName(s || null)}</option>)}</select></label>
        <label>역할<select className="fi" aria-label="역할 거르기" value={role} onChange={(e) => setRole(e.target.value)}>
          <option value="">모든 역할</option>
          {roles.map((x) => <option key={x} value={x}>{roleName(x || null)}</option>)}</select></label>
        <button type="button" className={'chip' + (slow ? ' on' : '')} aria-pressed={slow} onClick={() => setSlow(!slow)}>느린 순</button>
        {filtered && <button type="button" className="bo" onClick={() => { setStep(''); setRole(''); setSlow(false) }}>초기화</button>}
        <span className="en" style={{ marginLeft: 'auto' }}>{num(rows.length)} / {num(data.count)}건</span>
      </div>
      <table className="mini rlcalltbl"><thead><tr><th>시각</th><th>단계</th><th>역할</th><th>모델 · 판</th><th>걸린 시간</th><th>토큰 입력/출력</th><th>줄</th><th>결과</th></tr></thead>
        <tbody>
          {rows.length === 0 && <tr><td colSpan={8} className="rlempty">조건에 맞는 AI 호출이 없습니다. 단계나 역할을 바꾸거나 [초기화]를 누르세요.</td></tr>}
          {rows.map((c) => (
            <tr key={c.call_id}>
              <td>{stamp(c.started_at)}</td><td>{stepName(c.step)}</td>
              <td>{roleName(c.role)}{c.attempt > 0 && <span className="en"> 재시도 {c.attempt}</span>}</td>
              <td className="en">{c.model} · {c.prompt_version ?? '—'}</td>
              <td>{secs(c.duration_ms / 1000)}</td><td>{num(c.input_tokens)} / {num(c.output_tokens)}</td><td>{c.batch_lines || '—'}</td>
              <td>{c.result === 'OK' ? '성공' : <span className="c-ora">{RESULT_NAMES[c.result]}</span>}
                {c.dropped_reason && <div className="en">버림: {c.dropped_reason}</div>}</td>
            </tr>
          ))}
        </tbody></table>
    </>
  )
}
