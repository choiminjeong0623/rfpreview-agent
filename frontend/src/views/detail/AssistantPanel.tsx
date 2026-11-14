import { useEffect, useState } from 'react'
import { api, type AssistantAnswer, type AssistantEvidence, type RunDocument } from '../../api'
import { locName } from '../../components/judgment'
import { RESULT_NAMES, TYPE_NAMES } from '../../components/labels'
import './assistant.css'

// 검토 도우미 창 (add-review-assistant, update-assistant-panel, FR-17). docs/screens/SCR-08_공유.md
// AI는 읽기 도구(요구사항 찾기·판정 찾기·한 줄 보기)만 쓴다. 이 창에는 고치기 단추가 없다.

// AI가 없어도 글자 찾기로 결과가 나오는 낱말만 둔다. 한국어 질문 예시는 입력칸 안내 글에.
const EXAMPLES = ['ambient temperature', 'type test', 'witness']
const HANGUL = /[가-힣]/

function stepText(s: AssistantAnswer['steps'][number]): string {
  const found = ` — ${s.found}건`
  if (s.tool === 'get_requirement') return `${s.ref ?? ''} 원문 보기${found}`
  const where = s.tool === 'find_judgments'
    ? `판정${s.result ? `(${RESULT_NAMES[s.result] ?? s.result})` : ''}`
    : `요구사항${s.type_code ? `(${TYPE_NAMES[s.type_code] ?? s.type_code})` : ''}`
  return `${where}에서 ${s.words ? `‘${s.words}’ ` : ''}찾기${found}`
}

function Evidence({ e, no, docs }: { e: AssistantEvidence; no: number; docs: RunDocument[] }) {
  const tag = e.kind === 'JUDGMENT'
    ? `판정 ${RESULT_NAMES[e.result ?? ''] ?? e.result ?? ''}`
    : e.type_code ? (TYPE_NAMES[e.type_code] ?? e.type_code) : null
  const values = [e.req_value_raw && `요구값 ${e.req_value_raw}`, e.product_value_raw && `제품값 ${e.product_value_raw}`]
    .filter(Boolean).join(', ')
  return (
    <li id={`as-${e.ref}`} className="as-ev" data-testid="assistant-evidence">
      <div className="as-evh">
        <span className="as-no" title={`근거 번호 ${e.ref}`}>{no}</span>
        <span className="as-loc">{e.locations.map((l) => locName(l, docs)).join(' / ')}</span>
      </div>
      {(tag || e.item_name) && (
        <div className="as-tags">
          {tag && <span className="as-tag">{tag}</span>}
          {e.item_name && <span className="as-item">{e.item_name}</span>}
        </div>
      )}
      <p className="as-txt">{e.text_raw}</p>
      {values && <p className="as-val">{values}</p>}
    </li>
  )
}

function status(a: AssistantAnswer): string {
  if (a.mode === 'AI') {
    return `AI 답변 (근거와 대조함)${a.dropped > 0 ? ` · 근거와 맞지 않는 문장 ${a.dropped}개 뺌` : ''}`
  }
  return `검색어로 찾은 결과${a.note ? ` (${a.note})` : ''}`
}

export function AssistantPanel({ runId, docs, onClose }: { runId: number; docs: RunDocument[]; onClose: () => void }) {
  const [q, setQ] = useState('')
  const [asked, setAsked] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [answer, setAnswer] = useState<AssistantAnswer | null>(null)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  const send = (text: string) => {
    const question = text.trim()
    if (question.length < 2 || busy) return
    setBusy(true)
    setError(null)
    setAsked(question)
    api.ask(runId, question).then(setAnswer, (e: Error) => { setAnswer(null); setError(e.message) }).finally(() => setBusy(false))
  }
  const jump = (ref: string) => document.getElementById(`as-${ref}`)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  const numberOf = new Map((answer?.evidence ?? []).map((e, i) => [e.ref, i + 1]))
  const empty = answer && answer.sentences.length === 0 && answer.evidence.length === 0
  return (
    <aside className="as" role="dialog" aria-modal="false" aria-labelledby="asT">
      <div className="as-h">
        <h2 id="asT">검토 도우미</h2>
        <button type="button" className="ib" onClick={onClose} aria-label="닫기" title="닫기 (Esc)"><span className="ms" aria-hidden="true">close</span></button>
      </div>
      <form className="as-f" onSubmit={(e) => { e.preventDefault(); send(q) }}>
        <textarea className="fi" rows={2} value={q} maxLength={500} onChange={(e) => setQ(e.target.value)} aria-label="검토 도우미 질문"
          placeholder="예: 시험 성적서를 요구하는 조항만 보여 줘" onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(q) } }} />
        <button type="submit" className="bp" disabled={busy || q.trim().length < 2}>묻기</button>
      </form>
      <div className="as-ex" aria-label="예시 검색어">{EXAMPLES.map((x) => <button key={x} type="button" className="chip" disabled={busy} onClick={() => { setQ(x); send(x) }}>{x}</button>)}</div>
      <div className="as-b" aria-live="polite">
        {error && <p className="aphint" role="alert">{error}</p>}
        {!answer && !error && !busy && <p className="as-empty">이 검토의 요구사항과 판정에서만 찾습니다. 답에는 근거 조항이 붙고, 값은 바꾸지 않습니다.</p>}
        {busy && <p className="as-empty">찾는 중…</p>}
        {answer && !busy && (
          <>
            <p className="as-mode">{status(answer)}</p>
            {answer.sentences.length > 0 && (
              <ol className="as-ans">{answer.sentences.map((s, i) => (
                <li key={i}>{s.text}{s.evidence_ids.map((r) => (
                  <button key={r} type="button" className="as-cite" onClick={() => jump(r)} title={`근거 조항 ${numberOf.get(r) ?? ''}로 가기`}>[{numberOf.get(r) ?? r}]</button>
                ))}</li>
              ))}</ol>
            )}
            {empty && (
              <p className="as-none" role="status">
                {answer.mode === 'AI' ? answer.note : '일치하는 조항이 없습니다.'}
                {HANGUL.test(asked) && ' 문서가 영어라면 영어 낱말로 찾아 보세요 (예: witness, type test).'}
              </p>
            )}
            {answer.evidence.length > 0 && <><h3>근거 조항 {answer.evidence.length}건</h3>
              <ul className="as-evs">{answer.evidence.map((e, i) => <Evidence key={e.ref} e={e} no={i + 1} docs={docs} />)}</ul></>}
            {answer.steps.length > 0 && (
              <details className="as-how">
                <summary>찾은 방법 보기</summary>
                <ul className="as-steps">{answer.steps.map((s, i) => <li key={i}>{stepText(s)}</li>)}</ul>
              </details>
            )}
          </>
        )}
      </div>
    </aside>
  )
}
