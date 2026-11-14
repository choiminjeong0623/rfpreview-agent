import { useEffect, useRef, useState, type ChangeEvent } from 'react'
import { api, type DocumentChoice, type DocumentPreview, type RunDocument, type RunSummary } from '../api'
import { reviewTitle } from '../components/format'
import { CLASSIFY_BY, skipReason } from '../components/documents'
import { DOC_KIND_NAMES } from '../components/labels'
import { useSession } from '../shell/useSession'
import './detail.css'

// 검토 머리글 "문서 n개"를 누르면 열리는 문서 표 창 (SCR-08, change update-document-info).
// 문서마다 종류·분류 방법·묶음·판정 대상·요구사항 수·확인 필요를 보인다. 분석한 문서의 묶음은 여기서 고치지 않는다.
// 엔지니어는 담당자 확인 단계에서 정정본·추가 문서를 더해 다시 분석한다 (add-document-addendum).

type Kind = DocumentPreview['doc_kind']
type Bundle = DocumentPreview['bundle']
const KINDS = Object.keys(DOC_KIND_NAMES) as Kind[]
const BUNDLES: Bundle[] = ['A', 'B', 'C', 'D']

/** 문서 추가: docx·PDF 고르기 → 분류 추천 → 묶음·종류 고르기 → 추가하고 다시 분석 */
function AddDocuments({ run, docs, onAdded }: { run: RunSummary; docs: RunDocument[]; onAdded: () => void }) {
  const { user } = useSession()
  const input = useRef<HTMLInputElement>(null)
  const [files, setFiles] = useState<File[]>([])
  const [previews, setPreviews] = useState<Record<string, DocumentPreview> | 'loading' | null>(null)
  const [chosen, setChosen] = useState<Record<string, DocumentChoice>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const have = new Set(docs.map((d) => d.file_name))

  const pick = (e: ChangeEvent<HTMLInputElement>) => {
    const list = Array.from(e.target.files ?? []).filter((f) => /\.(docx|pdf)$/i.test(f.name))
    e.target.value = ''
    setError(null)
    setChosen({})
    setFiles(list)
    if (!list.length) { setPreviews(null); return }
    setPreviews('loading')
    api.previewUpload(list).then((rows) => setPreviews(Object.fromEntries(rows.map((r) => [r.file_name, r]))),
      () => setPreviews({}))
  }
  const now = (f: File): DocumentChoice | null => {
    const pv = typeof previews === 'object' && previews ? previews[f.name] : undefined
    return chosen[f.name] ?? (pv ? { doc_kind: pv.doc_kind, bundle: pv.bundle } : null)
  }
  const dup = files.filter((f) => have.has(f.name)).map((f) => f.name)
  const submit = () => {
    setBusy(true)
    setError(null)
    const choices: Record<string, DocumentChoice> = {}
    files.forEach((f) => { const c = now(f); if (c) choices[f.name] = c })
    api.addDocuments(run.run_id, files, choices, user?.user_id ?? null)
      .then(onAdded, (e: Error) => setError(e.message)).finally(() => setBusy(false))
  }
  return (
    <section className="docadd" aria-labelledby="docAddTitle">
      <h3 id="docAddTitle">문서 추가</h3>
      <p className="aphint" style={{ color: 'var(--c-muted)' }}>발주처가 낸 정정본·추가 문서(Addendum)를 더하면 처음 문서와 함께 이 검토를 다시 분석합니다.
        처리한 문서는 다시 쓰고, 확정·수정·반려한 판정과 위험 조건은 같은 줄이면 그대로 이어받습니다.</p>
      <input ref={input} type="file" accept=".docx,.pdf" multiple hidden onChange={pick} aria-label="추가할 파일 (docx·PDF)" />
      <button type="button" className="bo" onClick={() => input.current?.click()} disabled={busy}>
        <span className="ms" aria-hidden="true" style={{ fontSize: 'var(--ic-s)' }}>note_add</span>docx·PDF 고르기</button>
      {files.length > 0 && (
        <div className="tw" style={{ marginTop: 8 }}><table className="tbl doct">
          <thead><tr><th>파일 이름</th><th>문서 종류</th><th>묶음</th><th>판정</th></tr></thead>
          <tbody>
            {files.map((f) => {
              const c = now(f)
              const pv = typeof previews === 'object' && previews ? previews[f.name] : undefined
              return (
                <tr key={f.name}>
                  <td className="docn">{f.name}{have.has(f.name) && <div className="docwhy">이미 이 검토에 있는 파일입니다</div>}</td>
                  {previews === 'loading' ? <td className="dimv" colSpan={3}>분류하는 중…</td>
                    : c === null ? <td className="dimv" colSpan={3}>분석하면서 정합니다</td>
                      : <>
                        <td><select className="fi" aria-label="문서 종류" value={c.doc_kind ?? ''}
                          onChange={(e) => setChosen({ ...chosen, [f.name]: { ...c, doc_kind: e.target.value as Kind } })}>
                          {KINDS.map((k) => <option key={k} value={k}>{DOC_KIND_NAMES[k]}</option>)}
                        </select></td>
                        <td><select className="fi" aria-label="묶음" value={c.bundle ?? ''} style={{ width: 96 }}
                          onChange={(e) => setChosen({ ...chosen, [f.name]: { ...c, bundle: e.target.value as Bundle } })}>
                          {BUNDLES.map((b) => <option key={b} value={b}>묶음 {b}</option>)}
                        </select></td>
                        <td>{pv?.readable !== false && (c.bundle === 'A' || c.bundle === 'B')
                          ? <span className="st c-green">판정 대상</span> : <span className="st c-red">판정 안 함</span>}
                          {pv && <div className="en" style={{ margin: '4px 0 0' }}>{pv.reason}</div>}</td>
                      </>}
                </tr>
              )
            })}
          </tbody>
        </table></div>
      )}
      {error && <p className="docwhy" role="alert">{error}</p>}
      {files.length > 0 && (
        <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <button type="button" className="bp" onClick={submit} disabled={busy || previews === 'loading' || dup.length > 0}>
            {busy ? '보내는 중…' : `추가하고 다시 분석 (${files.length}개)`}</button>
          <span className="aphint" style={{ margin: 0, color: 'var(--c-muted)' }}>분석하는 동안 검토는 처리 중으로 바뀝니다.</span>
        </div>
      )}
    </section>
  )
}

export function DocumentsDialog({ run, docs, onClose, onAdded }: {
  run: RunSummary; docs: RunDocument[]; onClose: () => void; onAdded?: () => void
}) {
  const { user } = useSession()
  const canAdd = !!onAdded && run.stage === 'ENGINEER_REVIEW' && user?.role === 'ENGINEER'
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  const judged = docs.filter((d) => d.judge_target).length
  const review = docs.filter((d) => d.needs_review).length
  return (
    <div className="mdo" onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="apw docw" role="dialog" aria-modal="true" aria-labelledby="docsTitle">
        <div className="mdh">
          <div style={{ flex: '1 1 auto', minWidth: 0 }}>
            <div className="apid">{run.review_no} · {reviewTitle(run)}</div>
            <h2 id="docsTitle" style={{ margin: '2px 0 0', fontSize: 'var(--fs-h3)' }}>문서 {docs.length}개</h2>
          </div>
          <button type="button" className="ib" onClick={onClose} aria-label="닫기" title="닫기 (Esc)"><span className="ms" aria-hidden="true">close</span></button>
        </div>
        <div className="apb">
          <p className="docsum">판정 대상 <b>{judged}개</b> · 판정 안 함 <b className={judged < docs.length ? 'c-red' : ''}>{docs.length - judged}개</b>
            {review > 0 && <> · 확인 필요 <b className="c-ora">{review}개</b></>}</p>
          <div className="tw"><table className="tbl doct">
            <thead><tr><th>파일</th><th>파일 이름</th><th>문서 종류</th><th>분류 방법</th><th>묶음</th><th>판정</th><th>요구사항</th></tr></thead>
            <tbody>
              {docs.map((d) => (
                <tr key={d.document_id} className={d.judge_target ? '' : 'skip'}>
                  <td>{d.file_no}</td>
                  <td className="docn">{d.file_name}</td>
                  <td>{DOC_KIND_NAMES[d.doc_kind] ?? d.doc_kind}
                    {d.needs_review && <> <span className="st c-ora">확인 필요</span></>}</td>
                  <td>{CLASSIFY_BY[d.classify_by ?? ''] ?? '—'}</td>
                  <td>묶음 {d.bundle}</td>
                  <td>{d.judge_target
                    ? <span className="st c-green">판정 대상</span>
                    : <><span className="st c-red">판정 안 함</span><div className="docwhy">{skipReason(d)}</div></>}</td>
                  <td>{d.requirements.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table></div>
          <p className="aphint" style={{ color: 'var(--c-muted)' }}>판정은 판정 대상(묶음 A·B) 문서에만 합니다. 분석한 문서의 종류·묶음은 이 창에서 고칠 수 없습니다.</p>
          {canAdd && <AddDocuments run={run} docs={docs} onAdded={() => { onClose(); onAdded?.() }} />}
        </div>
        <div className="mdf">
          <button type="button" className="bo" onClick={onClose}>닫기</button>
        </div>
      </div>
    </div>
  )
}
