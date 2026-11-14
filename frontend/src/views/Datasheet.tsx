import { useState } from 'react'
import { api, type DatasheetRow } from '../api'
import { ErrorText } from '../components/common'
import { Pager } from '../components/Pager'
import { saveFile } from '../components/download'
import { stamp } from '../components/format'
import { useLoad } from '../components/useLoad'
import { useCrumbTail } from '../shell/crumb'
import { usePageCss } from '../shell/pageCss'
import { href } from '../shell/router'
import { useSession } from '../shell/useSession'
import { useToast } from '../ui'

// SCR-10 데이터시트 채우기 (목업 v4.57 Datasheet). docs/screens/SCR-10-데이터시트.md
// 고객 표 하나의 칸 순서 그대로. 근거 값이 없는 칸은 비워 두고 "확인 필요" (CR-04). 화면과 엑셀이 같은 줄.
// 영업에 넘기기(add-submission-package): 엔지니어만, 후보 칸이 없을 때만(CR-08). 넘긴 기록은 /handoffs.

type Filter = 'all' | 'cand' | 'empty' | 'ok'
const FILTERS: [Filter, string][] = [['all', '전체'], ['cand', '후보'], ['empty', '확인 필요'], ['ok', '확정']]
const TONES: Record<DatasheetRow['state'], string> = { ok: 'st c-green', cand: 'st c-blue', empty: 'st c-ora' }
const SENDABLE = ['ENGINEER_REVIEW', 'APPROVAL', 'APPROVED']
const pct = (n: number, total: number) => `${total ? Math.round((n / total) * 100) : 0} %`

export function Datasheet({ runId }: { runId: number }) {
  usePageCss('Datasheet')
  const { user } = useSession()
  const [chosen, setChosen] = useState<number | null>(null)
  const [flt, setFlt] = useState<Filter>('all')
  const [page, setPage] = useState(1)
  const [size, setSize] = useState(10)
  const [tick, setTick] = useState(0)
  const [busy, setBusy] = useState(false)
  const [sending, setSending] = useState(false)
  const [confirming, setConfirming] = useState<string | null>(null)
  const toast = useToast()
  const [error, setError] = useState<string | null>(null)
  const run = useLoad(() => api.run(runId), [runId])
  const sheets = useLoad(() => api.datasheets(runId), [runId, tick])
  // 처음에는 빈 칸이 가장 많은 표를 연다
  const first = sheets.data?.length ? [...sheets.data].sort((a, b) => b.empty - a.empty)[0].table_id : null
  const tableId = chosen ?? first
  const data = useLoad(() => (tableId === null ? Promise.resolve(null) : api.datasheet(runId, tableId)), [runId, tableId, tick])
  const sent = useLoad(() => api.handoffs(runId), [runId, tick])
  useCrumbTail(run.data?.review_no)

  const r = run.data
  const d = data.data
  const c = d?.counts
  const canEdit = r?.stage === 'ENGINEER_REVIEW' && user?.role === 'ENGINEER'
  const found = d?.rows.filter((x) => flt === 'all' || x.state === flt) ?? []
  const rows = found.slice((page - 1) * size, page * size)
  const say = (m: string) => toast.done(m)
  const confirm = (x: DatasheetRow) => {
    setError(null)
    setConfirming(x.no)
    const body = x.target === 'warranty'
      ? { target: 'warranty_candidate', target_id: x.candidate_id!, action: 'CONFIRM' }
      : { target: 'judgment', target_id: x.judgment_id, action: 'CONFIRM' }
    api.act(runId, { ...body, actor_id: user!.user_id }).then(() => {
      setTick((t) => t + 1)
      say(`칸 ${x.no} ${x.item} 값을 확정했습니다.`)
    }, (e: Error) => setError(e.message)).finally(() => setConfirming(null))
  }
  const download = () => {
    if (busy || tableId === null) return
    setBusy(true)
    setError(null)
    api.exportDatasheet(runId, tableId).then(({ name, blob }) => {
      saveFile(name, blob)
      say(`${name} 를 내려받았습니다. 고객 양식 칸 순서 그대로입니다.`)
    }, (e: Error) => setError(e.message)).finally(() => setBusy(false))
  }
  const last = sent.data?.find((h) => h.kind === 'DATASHEET' && h.table_id === tableId)
  const sendBlock = !r || !d ? '불러오는 중입니다'
    : user?.role !== 'ENGINEER' ? '영업에 넘기기는 기술 검토 엔지니어만 할 수 있습니다'
      : !SENDABLE.includes(r.stage) ? '담당자 확인 단계부터 영업에 넘길 수 있습니다'
        : d.rows.length === 0 ? '넘길 칸이 없습니다'
          : c && c.cand > 0 ? `후보 ${c.cand}칸을 먼저 확정해 주세요. 사람이 확인하지 않은 값은 넘기지 않습니다`
            : null
  const handoff = () => {
    if (sending || sendBlock || tableId === null) return
    setSending(true)
    setError(null)
    api.handoffDatasheet(runId, tableId, user!.user_id).then((res) => {
      setTick((t) => t + 1)
      if (res.sent) say(`영업 담당(${res.mail_to})에게 넘겼습니다. 확인 필요 ${res.empty ?? 0}칸은 비운 채로 넘어갑니다.`)
      else setError(res.error === '주소 없음' ? '영업 담당 메일 주소가 설정되지 않아 넘기지 못했습니다. 시스템 담당자에게 문의하세요.' : `영업에 넘기지 못했습니다: ${res.error}`)
    }, (e: Error) => setError(e.message)).finally(() => setSending(false))
  }
  const sub = d && r ? [d.table_name, d.source_file, r.project_name, r.review_no].filter(Boolean).join(' · ') : ''

  return (
    <main className="main">
      <div className="ttl">
        <div><h1>데이터시트 채우기</h1><p className="tb-sub">{sub}</p></div>
        <div style={{ display: 'flex', gap: 8 }}>
          <a className="bo" href={href(`/reviews/${runId}`)}><span className="ms" aria-hidden="true" style={{ fontSize: 'var(--ic-s)' }}>arrow_back</span>검토 상세로</a>
          <span title={sendBlock ?? undefined}><button type="button" className="bo" onClick={handoff} disabled={sending || sendBlock !== null}>
            <span className="ms" aria-hidden="true" style={{ fontSize: 'var(--ic-s)' }}>forward_to_inbox</span>
            {sending ? '넘기는 중…' : last && !last.mail_error ? '다시 넘기기' : '영업에 넘기기'}</button></span>
          <span title={d && d.rows.length === 0 ? '내려받을 칸이 없습니다' : undefined}>
            <button type="button" className="bp" onClick={download} disabled={busy || !d || d.rows.length === 0}>
              <span className="ms" aria-hidden="true" style={{ fontSize: 'var(--ic-s)' }}>download</span>{busy ? '만드는 중…' : '엑셀 내려받기'}</button></span>
        </div>
      </div>
      <div className="sh-note"><span className="ms" aria-hidden="true">info</span><span>보증값은 제안 영업이 고객에게 내는 값입니다. 이 화면은 <b>엔지니어가 확정한 후보를 영업에 넘기는 초안</b>입니다. 고객 양식의 칸 순서를 그대로 두고, 제품표·성적서에 없는 값은 채우지 않고 "확인 필요"로 남깁니다. 납기·보증 기간 같은 상업 정보는 영업이 오퍼시트에 적습니다.</span></div>
      {(last || (c && c.cand > 0 && user?.role === 'ENGINEER')) && (
        <p className="ds-sent">
          {last && (last.mail_error
            ? <span className="c-red">{stamp(last.sent_at)} 영업에 넘기지 못함: {last.mail_error === '주소 없음' ? '영업 주소 없음' : '발송 실패'}</span>
            : <span>{stamp(last.sent_at)} 영업 담당({last.mail_to})에게 넘김 · {last.sent_by_name}</span>)}
          {c && c.cand > 0 && user?.role === 'ENGINEER' && <span className="c-ora">{last ? ' · ' : ''}후보 {c.cand}칸을 먼저 확정해야 영업에 넘길 수 있습니다.</span>}
        </p>
      )}
      <div className="ds-k" aria-label="요약">
        <div><span>제출할 칸</span><b>{c?.rows ?? '—'}</b><em>고객 양식 그대로</em></div>
        <div><span>채움 · 확정</span><b className="c-green">{c?.ok ?? '—'}</b><em>엔지니어 확정</em></div>
        <div><span>채움 · 후보</span><b className="c-blue">{c?.cand ?? '—'}</b><em>확정 전</em></div>
        <div><span>확인 필요 (빈칸)</span><b className="c-ora">{c?.empty ?? '—'}</b><em>{c ? `지금 ${pct(c.empty, c.rows)}` : ''}</em></div>
        <div><span>중복 칸</span><b>—</b><em>다른 섹션 같은 칸은 찾지 않음</em></div>
      </div>
      {c && (
        <div className="ds-bar"><div className="ds-fill"><i className="ok" style={{ width: pct(c.ok, c.rows).replace(' ', '') }} />
          <i className="cand" style={{ width: pct(c.cand, c.rows).replace(' ', '') }} /></div>
          <span className="sh-mut">{c.rows}칸 중 {c.ok + c.cand}칸 채움 ({pct(c.ok + c.cand, c.rows)}) · 남은 빈칸 {c.empty}칸</span></div>
      )}
      <div className="sp" style={{ marginTop: 16 }}><div className="sp-r1">
        <label className="sp-f"><span className="sp-l">데이터시트</span>
          <select className="fi" value={tableId ?? ''} onChange={(e) => { setChosen(Number(e.target.value)); setFlt('all'); setPage(1) }}>
            {sheets.data?.map((s) => <option key={s.table_id} value={s.table_id}>{s.table_name} · {s.file_name} ({s.rows}칸)</option>)}
          </select></label>
        <div className="sp-f" role="radiogroup" aria-label="보기"><span className="sp-l">보기</span>
          {FILTERS.map(([k, label]) => (
            <label key={k} className="sp-rd"><input type="radio" name="flt" checked={flt === k} onChange={() => { setFlt(k); setPage(1) }} />{label}</label>
          ))}</div>
      </div></div>
      <ErrorText error={sheets.error ?? data.error ?? run.error ?? error} />
      {sheets.data && sheets.data.length === 0 && <p style={{ color: 'var(--c-muted)' }}>이 검토에는 채울 데이터시트(판정이 있는 고객 표)가 없습니다.</p>}
      <section className="sec" style={{ marginTop: 20 }}>
        <div className="tw"><table className="tbl ds-t">
          <thead><tr><th style={{ width: 46 }}>칸</th><th>항목</th><th style={{ width: 64 }}>단위</th><th>고객 요구</th><th>채운 값 (보증값 후보)</th><th>근거</th><th style={{ width: 140 }}>상태</th></tr></thead>
          <tbody>{rows.map((x) => (
            <tr key={x.judgment_id} className={x.state === 'empty' ? 'ds-empty' : ''}>
              <td className="mono" style={{ color: 'var(--c-muted)' }}>{x.no}</td>
              <td><b style={{ fontWeight: 600 }}>{x.item}</b>{x.item_en && x.item_en !== x.item && <div className="tb-en">{x.item_en}</div>}</td>
              <td className="mono">{x.unit}</td>
              <td>{x.requirement}</td>
              <td>{x.value ? <b className="ds-v">{x.value}</b> : <span className="ds-e">비움</span>}</td>
              <td className="ds-b">{x.basis}{!x.value && <span className="c-ora">{x.why}</span>}</td>
              <td><span className={TONES[x.state]}>{x.status}</span>
                {x.state === 'cand' && canEdit && <button type="button" className="ds-ok" onClick={() => confirm(x)} disabled={confirming !== null} aria-label={`칸 ${x.no} ${x.item} 확정`}>{confirming === x.no ? '확정하는 중…' : '확정'}</button>}</td>
            </tr>
          ))}</tbody>
        </table></div>
        {found.length > 0 && <Pager total={found.length} page={page} size={size} shown={rows.length} onPage={setPage} onSize={(n) => { setSize(n); setPage(1) }} />}
        {d && rows.length === 0 && <p style={{ margin: 0, padding: '16px 12px', color: 'var(--c-muted)' }}>이 보기에 맞는 칸이 없습니다.</p>}
      </section>
    </main>
  )
}
