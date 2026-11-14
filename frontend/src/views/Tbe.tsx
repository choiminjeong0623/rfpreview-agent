import { useState } from 'react'
import { api, type TbeQuery } from '../api'
import { ErrorText } from '../components/common'
import { Pager } from '../components/Pager'
import { saveFile } from '../components/download'
import { stamp } from '../components/format'
import { useLoad } from '../components/useLoad'
import { useCrumbTail } from '../shell/crumb'
import { usePageCss } from '../shell/pageCss'
import { href } from '../shell/router'
import { useToast } from '../ui'

// SCR-09 TBE 준수표 (목업 v4.57 Tbe). docs/screens/SCR-09-TBE준수표.md
// 미리보기와 엑셀은 같은 API 줄을 쓴다. 원문 위치가 없는 판정은 넣지 않는다 (CR-03).

const VERDICT_TONES: Record<string, string> = {
  COMPLY: 'st c-green', DEVIATION_CANDIDATE: 'st c-red', QUERY_CANDIDATE: 'st c-ora', NEEDS_REVIEW: 'st c-ora',
}
const INCLUDE: [TbeQuery['include'], string][] = [['all', '후보 포함 (후보 꼬리표)'], ['confirmed', '확정 항목만']]
const LANG: [TbeQuery['lang'], string][] = [['en', '영문 (제출용)'], ['ko', '국문'], ['both', '영문 + 국문']]

export function Tbe({ runId }: { runId: number }) {
  usePageCss('Tbe')
  const [include, setInclude] = useState<TbeQuery['include']>('all')
  const [lang, setLang] = useState<TbeQuery['lang']>('en')
  const [base, setBase] = useState<TbeQuery['base']>('now')
  const [opened] = useState(() => new Date().toISOString())
  const [busy, setBusy] = useState(false)
  const toast = useToast()
  const [error, setError] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [size, setSize] = useState(10)
  const run = useLoad(() => api.run(runId), [runId])
  const q: TbeQuery = { include, lang, base }
  const data = useLoad(() => api.tbe(runId, q), [runId, include, lang, base])
  useCrumbTail(run.data?.review_no)

  const r = run.data
  const d = data.data
  const c = d?.counts
  const shown = d?.rows.slice((page - 1) * size, page * size) ?? []
  const approved = r?.stage === 'APPROVED'
  const sub = r ? [r.project_name, r.review_name, r.review_no, r.customer_name].filter(Boolean).join(' · ') : ''
  const download = () => {
    if (busy) return
    setBusy(true)
    setError(null)
    api.exportTbe(runId, q).then(({ name, blob }) => {
      saveFile(name, blob)
      toast.done(`${name} 를 내려받았습니다 (${c?.rows ?? 0}건).`)
    }, (e: Error) => setError(e.message)).finally(() => setBusy(false))
  }

  return (
    <main className="main">
      <div className="ttl">
        <div><h1>TBE 준수표</h1><p className="tb-sub">{sub}</p></div>
        <div style={{ display: 'flex', gap: 8 }}>
          <a className="bo" href={href(`/reviews/${runId}`)}><span className="ms" aria-hidden="true" style={{ fontSize: 'var(--ic-s)' }}>arrow_back</span>검토 상세로</a>
          <span title={d && d.rows.length === 0 ? '내려받을 항목이 없습니다' : undefined}>
            <button type="button" className="bp" onClick={download} disabled={busy || !d || d.rows.length === 0}>
              <span className="ms" aria-hidden="true" style={{ fontSize: 'var(--ic-s)' }}>download</span>{busy ? '만드는 중…' : '엑셀 내려받기'}</button></span>
        </div>
      </div>
      <div className="sh-note"><span className="ms" aria-hidden="true">info</span><span>1차 입찰 후 고객과의 기술 평가(TBE) 미팅에서 요구사항마다 준수 여부를 함께 보는 표입니다. 사람이 확정하지 않은 줄은 <b>"후보"</b>로 찍히고, 원문 위치가 없는 줄은 넣지 않습니다. 점수 예측은 하지 않습니다.</span></div>
      <div className="sp" style={{ marginTop: 16 }}>
        <div className="sp-r1">
          <label className="sp-f"><span className="sp-l">판정 기준</span>
            <select className="fi" value={base} onChange={(e) => setBase(e.target.value as TbeQuery['base'])}>
              <option value="now">현재 판정 ({stamp(opened)})</option>
              <option value="v1" disabled={!approved}>{approved ? '제출본 v1 (결재 승인)' : '제출본 v1 (결재 승인 후 생김)'}</option>
            </select></label>
          <div className="sp-f" role="radiogroup" aria-label="포함 항목"><span className="sp-l">포함 항목</span>
            {INCLUDE.map(([k, label]) => (
              <label key={k} className="sp-rd"><input type="radio" name="inc" checked={include === k} onChange={() => { setInclude(k); setPage(1) }} />{label}</label>
            ))}</div>
          <div className="sp-f" role="radiogroup" aria-label="언어"><span className="sp-l">항목 언어</span>
            {LANG.map(([k, label]) => (
              <label key={k} className="sp-rd"><input type="radio" name="lang" checked={lang === k} onChange={() => setLang(k)} />{label}</label>
            ))}</div>
        </div>
      </div>
      <div className="sh-sum" aria-label="요약">
        <span>포함 항목<b>{c?.rows ?? '—'}</b></span><span>준수<b className="c-green">{c?.comply ?? '—'}</b></span>
        <span>일탈<b className="c-red">{c?.deviation ?? '—'}</b></span><span>질의<b className="c-ora">{c?.query ?? '—'}</b></span>
        <span>확인 필요<b className="c-ora">{c?.review ?? '—'}</b></span><span>그중 후보<b>{c?.candidates ?? '—'}</b></span>
        <span>원문 위치 없음(제외)<b>{c?.no_location ?? '—'}</b></span>
      </div>
      <ErrorText error={data.error ?? run.error ?? error} />
      <section className="sec" style={{ marginTop: 24 }}>
        <div className="sech"><h2>미리보기 <span style={{ fontWeight: 400, color: 'var(--c-muted)' }}>{d?.file_name}</span></h2></div>
        <div className="tw" style={{ marginTop: 12 }}><table className="tbl tb-t">
          <thead><tr><th style={{ width: 52 }}>No.</th><th>{lang === 'ko' ? '항목' : 'Item'}</th><th>고객 요구</th><th style={{ width: 110 }}>준수 여부</th>
            <th>우리 제품값</th><th>원문 위치 (파일 · 절 · 표 · 행)</th><th style={{ width: 70 }}>상태</th></tr></thead>
          <tbody>{shown.map((x) => (
            <tr key={x.judgment_id}>
              <td className="mono" style={{ color: 'var(--c-muted)' }}>{x.no}</td>
              <td><b style={{ fontWeight: 600 }}>{x.item}</b>{x.item_ko && <div className="tb-en">{x.item_ko}</div>}</td>
              <td style={{ whiteSpace: 'nowrap' }}>{x.requirement}</td>
              <td><span className={VERDICT_TONES[x.result]}>{x.verdict}</span></td>
              <td>{x.offered}</td>
              <td className="tb-loc"><span className="ell">{x.file_name}</span><span>{x.where}</span></td>
              <td><span className={x.confirmed ? 'st c-green' : 'st c-grey'}>{x.confirmed ? '확정' : '후보'}</span>{x.assumed && <div className="tb-en">팀 가정</div>}</td>
            </tr>
          ))}</tbody>
        </table></div>
        {d && d.rows.length > 0 && <Pager total={d.rows.length} page={page} size={size} shown={shown.length} onPage={setPage} onSize={(n) => { setSize(n); setPage(1) }} />}
        {d && d.rows.length === 0 && <p style={{ margin: 0, padding: '16px 12px', color: 'var(--c-muted)' }}>포함할 항목이 없습니다.</p>}
        {c && c.no_location > 0 && (
          <details className="tb-x"><summary>원문 위치가 없어 제외한 항목 {c.no_location}건</summary>
            <ul><li>원문 위치가 없는 판정은 근거를 가리킬 수 없어 넣지 않습니다. 질의서·일탈 목록에서 다룹니다.</li></ul></details>
        )}
      </section>
    </main>
  )
}
