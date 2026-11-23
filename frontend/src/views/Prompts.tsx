import { useEffect, useState } from 'react'
import { api, type PromptDetail, type PromptEvalJob, type PromptRole, type PromptVersion } from '../api'
import './detail.css'
import { stamp } from '../components/format'
import { useLoad } from '../components/useLoad'
import { usePageCss } from '../shell/pageCss'
import { useSession } from '../shell/useSession'
import { Badge, Button, Spinner, useToast } from '../ui'

// SCR-26 프롬프트 관리 (목업에 없음, add-prompt-view). docs/screens/SCR-26_공유.md
// Langfuse가 없으면 보기만 한다. 프롬프트 글과 판은 코드에서 고치고, 판을 올리면 해시 테스트와 평가를 거친다.
// Langfuse를 켜면(add-langfuse-prompts) 글은 Langfuse에 저장되고, 어디서 가져왔는지 본다.
// 줄을 누르면 오른쪽 패널(add-prompt-editor): 판 기록과 프롬프트 글. Langfuse가 연결되어 있으면
// 고친 글을 staging에 저장 → [평가 돌리기] → 통과하면 승인자가 [운영으로 올리기].

const num = (n: number) => n.toLocaleString('en-US')
const day = (iso: string | null) => (iso ? stamp(iso) : '—')

/** 그 판의 가장 최근 평가: 주 지표 반복 최솟값 */
function Score({ v, evaluated }: { v: PromptVersion; evaluated: boolean }) {
  if (!evaluated) return <span className="dimv">평가 문항 없음</span>
  if (!v.eval) return <span className="dimv">평가 기록 없음</span>
  const e = v.eval
  return (
    <span title={`평가 ${e.eval_id} · 평가셋 ${e.set_name} · ${e.model ?? '모델 모름'}`}>
      {e.metric} <b>{e.min === null ? '—' : `${e.min.toFixed(1)} %`}</b>
      {e.weak && <> <Badge tone="grey" title="사람이 확인하지 않은 정답(Claude 초안)만으로 잰 점수">근거 약함</Badge></>}
      {e.is_baseline && <> <Badge tone="blue">기준선</Badge></>}
      <div className="en">{day(e.created_at)}
        {e.langfuse_url && <> · <LangfuseLink url={e.langfuse_url} /></>}</div>
    </span>
  )
}

/** 평가를 Langfuse 실험으로 남겼으면 그 데이터셋 화면 (add-langfuse-experiments). 줄 누르기와 겹치지 않게 */
function LangfuseLink({ url }: { url: string }) {
  return <a className="lnk" href={url} target="_blank" rel="noreferrer" onClick={(ev) => ev.stopPropagation()}
    title="반복마다 실험 하나, 문항별 답과 정답 여부 점수">Langfuse에서 보기 ↗</a>
}

/** 지금 판을 가져온 곳. 코드로 돌아간 것은 사용자 잘못이 아니라 중립색 */
function Source({ r, on }: { r: PromptRole; on: boolean }) {
  if (r.prompt_source === 'LANGFUSE') {
    return <span><Badge tone="blue">Langfuse</Badge> <span className="en">{r.langfuse_name} v{r.langfuse_version}</span></span>
  }
  return (
    <span><Badge tone="grey">코드</Badge>
      {on && r.fallback && <div className="dimv" title={`Langfuse 프롬프트 ${r.langfuse_name}`}>{r.fallback}</div>}
    </span>
  )
}

function History({ r }: { r: PromptRole }) {
  return (
    <table className="tbl" style={{ margin: '4px 0 8px' }}>
      <thead><tr>
        <th>판</th><th>처음 쓴 때</th><th>마지막으로 쓴 때</th>
        <th style={{ textAlign: 'right' }}>검토 실행</th><th style={{ textAlign: 'right' }}>AI 호출</th><th>평가</th>
      </tr></thead>
      <tbody>
        {[...r.versions].reverse().map((v) => (
          <tr key={v.version}>
            <td className="en"><b>{v.version}</b>{v.current && <> <Badge tone="green">지금 판</Badge></>}</td>
            <td>{day(v.first_used)}</td>
            <td>{day(v.last_used)}</td>
            <td style={{ textAlign: 'right' }}>{num(v.runs)}</td>
            <td style={{ textAlign: 'right' }}>{num(v.calls)}</td>
            <td><Score v={v} evaluated={r.evaluated} /></td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function Prompts() {
  usePageCss('Products')
  const data = useLoad(() => api.prompts(), [])
  const [open, setOpen] = useState<string | null>(null)
  const roles = data.data?.roles ?? []
  const cur = (r: PromptRole) => r.versions.find((v) => v.current)!
  const lf = data.data?.langfuse
  const openRole = roles.find((r) => r.role === open) ?? null
  const fromLf = roles.filter((r) => r.prompt_source === 'LANGFUSE').length

  return (
    <main className="main">
      <div className="idl"><span>{lf?.enabled ? '고치기·평가' : '보기 전용'}</span>
        {lf?.enabled
          ? <span>프롬프트 글은 Langfuse에 저장됩니다 · <span className="en">{lf.host}</span> · 가져오는 표시 <span className="en">{lf.label}</span></span>
          : <span>프롬프트 글은 코드에서만 고칩니다{data.data && <> · <span className="en">{data.data.source}</span></>}</span>}
      </div>
      <div className="ttl"><div><h1>프롬프트 관리</h1>
        <p className="tb-sub">AI 역할마다 지금 쓰는 프롬프트 판과 판 기록, 판별 평가 점수를 봅니다. {lf?.enabled
          ? '고친 판은 staging 표시로 평가해 기준선보다 나빠지지 않을 때만 운영(production)으로 옮깁니다.'
          : '판을 올리면 해시 테스트와 프롬프트 평가를 거칩니다.'}</p></div></div>
      <div className="kpis">
        <div className="kpi"><div className="l">AI 역할</div><b>{data.data ? roles.length : '—'}</b><div className="s">평가 문항이 있는 역할 {roles.filter((r) => r.evaluated).length}개</div></div>
        {lf?.enabled && <div className="kpi"><div className="l">Langfuse에서 가져온 역할</div><b>{fromLf}</b><div className="s">나머지 {roles.length - fromLf}개는 코드 판</div></div>}
        <div className="kpi"><div className="l">판을 올린 역할</div><b>{data.data ? roles.filter((r) => r.versions.length > 1).length : '—'}</b><div className="s">쓴 기록에 판이 둘 이상</div></div>
        <div className="kpi"><div className="l">문서 처리 재사용 열쇠</div><b className="en">{data.data?.doc_key ?? '—'}</b><div className="s">문서 분류·문장 구분·유형 판. 바뀌면 같은 파일도 새로 처리</div></div>
      </div>
      <div className={`work${open ? ' open' : ''}`} style={{ marginTop: 16, ...(open ? { gridTemplateColumns: 'minmax(0,1fr) 560px' } : {}) }}>
        <div className="tw">
          <table className="tbl">
            <thead><tr>
              <th>역할</th><th>지금 판</th><th>가져온 곳</th><th style={{ textAlign: 'right' }}>판 수</th>
              <th style={{ textAlign: 'right' }}>지금 판 검토 실행</th><th>지금 판 마지막 사용</th><th>지금 판 평가</th>
            </tr></thead>
            <tbody>
              {data.data === null && !data.error && <tr><td colSpan={7} className="dimv">불러오는 중…</td></tr>}
              {data.error && <tr><td colSpan={7} className="c-red">{data.error}</td></tr>}
              {roles.map((r) => {
                const c = cur(r)
                return (
                  <tr key={r.role} className={open === r.role ? 'cur' : undefined} style={{ cursor: 'pointer' }} aria-selected={open === r.role}
                    tabIndex={0} onClick={() => setOpen(open === r.role ? null : r.role)}
                    onKeyDown={(e) => { if (e.key === 'Enter') setOpen(open === r.role ? null : r.role) }}>
                    <td><b>{r.label}</b> <span className="en">{r.role}</span>
                      {r.in_doc_key && <div className="en" title="이 판이 바뀌면 같은 파일도 새로 처리합니다">재사용 열쇠에 들어감</div>}</td>
                    <td className="en"><b>{r.current}</b></td>
                    <td><Source r={r} on={!!lf?.enabled} /></td>
                    <td style={{ textAlign: 'right' }}>{r.versions.length}</td>
                    <td style={{ textAlign: 'right' }}>{num(c.runs)}</td>
                    <td>{day(c.last_used)}</td>
                    <td><Score v={c} evaluated={r.evaluated} /></td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          <div className="tfoot"><span>줄을 누르면 오른쪽에 판 기록과 프롬프트 글이 열립니다.</span></div>
        </div>
        {openRole && <PromptPanel r={openRole} onClose={() => setOpen(null)} onChanged={data.reload} />}
      </div>
    </main>
  )
}

/** 글에 든 {{이름}} 묶음 */
const slotsOf = (text: string) => new Set([...text.matchAll(/\{\{(\w+)\}\}/g)].map((m) => m[1]))

/** 오른쪽 패널: 판 기록, 프롬프트 글 보기·고치기, 평가, 운영으로 올리기 (add-prompt-editor) */
function PromptPanel({ r, onClose, onChanged }: { r: PromptRole; onClose: () => void; onChanged: () => void }) {
  const detail = useLoad(() => api.prompt(r.role), [r.role])
  const d = detail.data?.role === r.role ? detail.data : null
  return (
    <aside className="panel" aria-label={`${r.label} 프롬프트`}>
      <div className="ph">
        <div style={{ flex: '1 1 auto', minWidth: 0 }}><div className="en" style={{ margin: '0 0 2px' }}>{r.role} · 지금 판 {r.current}</div><h3>{r.label}</h3></div>
        <button type="button" className="ib" aria-label="닫기" onClick={onClose}><span className="ms" aria-hidden="true">close</span></button>
      </div>
      <div style={{ padding: '12px 16px 16px' }}>
        <h4 style={{ margin: '0 0 4px' }}>판 기록 <span className="en">최근 판이 위</span></h4>
        <History r={r} />
        {detail.error && <p role="alert" className="c-red">{detail.error}</p>}
        {!d && !detail.error && <p className="dimv">불러오는 중…</p>}
        {d && <Editor key={`${d.role}-${d.staging?.version ?? 0}-${d.production?.version ?? 0}`} d={d}
          onSaved={() => { detail.reload(); onChanged() }} />}
      </div>
    </aside>
  )
}

function Editor({ d, onSaved }: { d: PromptDetail; onSaved: () => void }) {
  const { user } = useSession()
  const toast = useToast()
  const start = d.staging?.text ?? d.production?.text ?? d.code_template
  const [text, setText] = useState(start)
  const [memo, setMemo] = useState('')
  const [busy, setBusy] = useState<'' | 'save' | 'eval' | 'promote'>('')
  const [job, setJob] = useState<PromptEvalJob | null>(d.evaluation)
  const need = d.slots
  const have = slotsOf(text)
  const missing = need.filter((x) => !have.has(x))
  const extra = [...have].filter((x) => !need.includes(x))
  const ruleOk = text.includes(d.data_rule)
  const editor = user && (user.role === 'ENGINEER' || user.role === 'APPROVER')
  const running = job?.status === 'RUNNING'

  // 평가가 도는 동안 3초마다 상태를 묻는다
  useEffect(() => {
    if (!running) return
    const t = setInterval(() => {
      api.promptEval(d.role).then((j) => {
        setJob(j)
        if (j && j.status !== 'RUNNING') toast.done(j.status === 'DONE' ? '평가가 끝났습니다.' : '평가를 끝내지 못했습니다.')
      }).catch(() => undefined)
    }, 3000)
    return () => clearInterval(t)
  }, [running, d.role, toast])

  if (!d.connected) {
    return (
      <>
        <h4 style={{ margin: '16px 0 4px' }}>프롬프트 글 <Badge tone="grey">코드 판 {d.code_version}</Badge></h4>
        <p className="dimv" style={{ margin: '0 0 8px' }}>{d.editable_reason} 지금은 코드에 있는 글을 씁니다.</p>
        <pre className="pt">{d.code_template}</pre>
      </>
    )
  }

  const saveWhy = !editor ? '엔지니어·승인자만 고칠 수 있습니다.'
    : text === (d.staging?.text ?? null) ? 'staging 판과 글이 같습니다.'
    : missing.length || extra.length ? '자리표시자를 코드 틀과 같게 맞추세요.'
    : !ruleOk ? '문서 본문 규칙 문장이 빠졌습니다.' : null
  const evalWhy = !d.evaluable ? '이 역할은 평가 문항이 없어 화면에서 평가할 수 없습니다.'
    : !d.ai_ready ? 'AI를 쓰지 않는 설정이라 평가할 수 없습니다.'
    : !editor ? '엔지니어·승인자만 평가를 돌릴 수 있습니다.'
    : !d.staging ? '먼저 staging에 저장하세요.'
    : !d.staging.usable ? `staging 판을 쓸 수 없습니다: ${d.staging.problem}`
    : text !== d.staging.text ? '고친 글을 staging에 저장한 뒤 평가하세요.'
    : running ? '평가가 돌고 있습니다.' : null
  const fresh = job && d.staging && job.staging_version === d.staging.version
  const promoteWhy = user?.role !== 'APPROVER' ? '운영으로 올리기는 승인자만 할 수 있습니다.'
    : !fresh ? '지금 staging 판으로 평가를 돌리세요.'
    : job!.status !== 'DONE' ? '평가가 끝나지 않았습니다.'
    : job!.promoted_version ? '이미 운영으로 올렸습니다.'
    : job!.promote_block

  const save = async () => {
    if (!user) return
    setBusy('save')
    try {
      const r = await api.savePrompt(d.role, text, memo)
      toast.done(`staging에 v${r.version}으로 저장했습니다. 평가를 돌려 점수를 확인하세요.`)
      setMemo('')
      onSaved()
    } catch (e) { toast.show((e as Error).message, 'error') } finally { setBusy('') }
  }
  const runEval = async () => {
    if (!user) return
    setBusy('eval')
    try { setJob(await api.evalPrompt(d.role)) } catch (e) { toast.show((e as Error).message, 'error') } finally { setBusy('') }
  }
  const promote = async () => {
    if (!user || !job) return
    setBusy('promote')
    try {
      const r = await api.promotePrompt(d.role, job.job_id)
      toast.done(`v${r.version}을 운영(production)으로 올렸습니다. 다음 검토부터 이 판을 씁니다.`)
      setJob({ ...job, promoted_version: r.version })
      onSaved()
    } catch (e) { toast.show((e as Error).message, 'error') } finally { setBusy('') }
  }

  return (
    <>
      <h4 style={{ margin: '16px 0 4px' }}>프롬프트 글 <span className="en">{d.langfuse_name}</span></h4>
      <div className="en" style={{ margin: '0 0 8px' }}>
        운영(production) {d.production ? <>v{d.production.version}{!d.production.usable && <> · 코드 판을 씀({d.production.problem})</>}</> : '판 없음 · 코드 판을 씀'}
        {' · '}staging {d.staging ? <>v{d.staging.version}{d.staging.commit_message && <> · {d.staging.commit_message}</>}</> : '판 없음'}
      </div>
      <label className="sr" htmlFor="pe-text">프롬프트 글</label>
      <textarea id="pe-text" className="pt" value={text} onChange={(e) => setText(e.target.value)} readOnly={!editor} spellCheck={false} rows={14} />
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, margin: '6px 0' }}>
        {need.map((x) => <Badge key={x} tone={have.has(x) ? 'green' : 'red'} title="코드가 채우는 자리. 지우거나 이름을 바꾸면 저장하지 않습니다">{`{{${x}}}`}</Badge>)}
        {extra.map((x) => <Badge key={x} tone="red" title="코드가 모르는 자리">{`{{${x}}} 모름`}</Badge>)}
        <Badge tone={ruleOk ? 'green' : 'red'} title={d.data_rule}>문서 본문 규칙</Badge>
      </div>
      <p className="en" style={{ margin: '0 0 8px' }}>숫자 계산·판정은 코드가 합니다. 글을 고쳐도 근거 대조·자리표시자 검사는 그대로입니다.</p>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <label className="sr" htmlFor="pe-memo">바꾼 이유</label>
        <input id="pe-memo" className="fi" style={{ flex: '1 1 auto' }} value={memo} maxLength={200} onChange={(e) => setMemo(e.target.value)} placeholder="바꾼 이유 (Langfuse 버전 메모)" />
        <Button kind="primary" icon="save" onClick={save} busy={busy === 'save'} disabledReason={saveWhy}>staging에 저장</Button>
      </div>

      <h4 style={{ margin: '20px 0 4px' }}>평가와 운영 반영</h4>
      <p className="dimv" style={{ margin: '0 0 8px' }}>공개 평가셋의 이 역할 문항을 staging 판으로 3번 묻고 기준선과 비교합니다. 나빠지지 않았을 때만 운영으로 올릴 수 있습니다.</p>
      <div style={{ display: 'flex', gap: 8 }}>
        <Button icon="science" onClick={runEval} busy={busy === 'eval'} disabledReason={evalWhy}>평가 돌리기</Button>
        <Button kind="primary" icon="rocket_launch" onClick={promote} busy={busy === 'promote'} disabledReason={promoteWhy ?? null}>운영으로 올리기</Button>
      </div>
      {job && <JobBox job={job} current={d.staging?.version ?? null} />}
    </>
  )
}

function JobBox({ job, current }: { job: PromptEvalJob; current: number | null }) {
  return (
    <div className="pjob" role="status">
      <div><b>staging v{job.staging_version} 평가</b> · {job.started_by} · {day(job.started_at)}
        {current !== null && current !== job.staging_version && <> · <span className="dimv">지금 staging과 다른 판</span></>}</div>
      {job.status === 'RUNNING' && <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginTop: 6 }}><Spinner /> 평가 중입니다. 몇 분 걸릴 수 있습니다.</div>}
      {job.status === 'FAILED' && <div className="c-red" style={{ marginTop: 6 }}>{job.message}</div>}
      {job.status === 'DONE' && (
        <>
          <table className="tbl" style={{ margin: '6px 0' }}><thead><tr><th>지표</th><th style={{ textAlign: 'right' }}>기준선</th><th style={{ textAlign: 'right' }}>이번(3번 중 최솟값)</th></tr></thead>
            <tbody>{job.metrics.map((m) => <tr key={m.name}><td>{m.name}</td>
              <td style={{ textAlign: 'right' }}>{m.baseline === null ? '—' : `${m.baseline.toFixed(1)} %`}</td>
              <td style={{ textAlign: 'right' }}><b>{m.now === null ? '—' : `${m.now.toFixed(1)} %`}</b></td></tr>)}</tbody></table>
          {job.regression ? <div className="c-red">기준선보다 나빠졌습니다: {job.reasons.join(' · ')}</div>
            : job.promote_block ? <div className="dimv">{job.promote_block}</div>
            : job.promoted_version ? <div><Badge tone="green">운영 반영</Badge> v{job.promoted_version}이 운영 판입니다.</div>
            : <div><Badge tone="green">통과</Badge> 운영으로 올릴 수 있습니다.</div>}
          {job.langfuse_url && <div style={{ marginTop: 4 }}><LangfuseLink url={job.langfuse_url} /></div>}
          {job.langfuse_error && <div className="dimv" style={{ marginTop: 4 }}>Langfuse에 실험을 남기지 못했습니다: {job.langfuse_error}</div>}
        </>
      )}
    </div>
  )
}
