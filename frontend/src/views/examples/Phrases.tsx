import { useState } from 'react'
import { Pager } from '../../components/Pager'
import { EXAMPLE_PHRASES, PHRASE_RELEASE, PHRASE_RELEASE_BY, type Phrase, type PhraseKind } from '../../examples/SCR-18'
import { usePageCss } from '../../shell/pageCss'
import { href } from '../../shell/router'
import { ExampleBand } from '../detail/ExampleTab'

// SCR-18 표준 문구 (목업 v4.57 Phrases). docs/screens/SCR-18-표준문구.md
// 표준 문구 저장소가 없어 예시로만 보여 준다. 문구 추가는 화면 안에서만 생기고 저장하지 않는다.

const KINDS: ['all' | PhraseKind, string][] = [['all', '전체'], ['dev', '일탈 문구'], ['qry', '질의 문구'], ['cf', '확인 요청']]
const KIND_NAMES: Record<PhraseKind, string> = { dev: '일탈 문구', qry: '질의 문구', cf: '확인 요청' }
const STATES: Record<Phrase[10], [string, string]> = { use: ['사용 중', 'st c-green'], rev: ['검토 중', 'st c-blue'], old: ['폐기', 'st c-grey'] }

/** 중괄호 { } 자리는 검토 값으로 바뀌는 칸이라 색을 달리한다 */
function Segs({ text }: { text: string }) {
  return <>{text.split(/(\{[^}]+\})/).filter(Boolean).map((t, i) => <span key={i} className={t[0] === '{' ? 'ph-var' : ''}>{t}</span>)}</>
}

export function Phrases() {
  usePageCss('Phrases')
  const [kind, setKind] = useState<'all' | PhraseKind>('all')
  const [q, setQ] = useState('')
  const [showOld, setShowOld] = useState(false)
  const [open, setOpen] = useState<Record<string, boolean>>({})
  const [drafts, setDrafts] = useState<Phrase[]>([])
  const [page, setPage] = useState(1)
  const [size, setSize] = useState(10)
  const [toast, setToast] = useState('')

  const needle = q.trim().toLowerCase()
  const vis = [...drafts, ...EXAMPLE_PHRASES].filter((r) => (showOld || r[10] !== 'old') && (!needle || (r[0] + r[2] + r[3] + r[4]).toLowerCase().includes(needle)))
  const found = vis.filter((r) => kind === 'all' || r[1] === kind)
  const rows = found.slice((page - 1) * size, page * size)
  const say = (m: string) => { setToast(m); setTimeout(() => setToast(''), 3000) }
  const addDraft = () => {
    const code = 'DV-' + String(4 + drafts.length + 1).padStart(2, '0')
    const draft: Phrase = [code, 'dev', '새 문구 초안 — 쓰는 상황을 적어 주세요', 'The offered {제품} ...', '제안 제품 {제품} ...', '—',
      '초안 · 10-24 기술 검토 엔지니어 A', 0, '기술 검토 엔지니어 A', '10-24', 'rev']
    setDrafts([draft, ...drafts])
    setKind('all')
    setPage(1)
    setOpen({ ...open, [code]: true })
    say(`${code} 초안을 만들었습니다. 팀 검토 후 사용 중으로 바뀝니다. (예시 화면이라 저장하지 않습니다)`)
  }
  const copy = (code: string, en: string) => {
    navigator.clipboard?.writeText(en).catch(() => undefined)
    say(`${code} 영문 문구를 복사했습니다.`)
  }

  return (
    <main className="main">
      <ExampleBand />
      <div className="ttl"><h1>표준 문구</h1><button type="button" className="bp" onClick={addDraft}><span className="ms" aria-hidden="true" style={{ fontSize: 'var(--ic-s)' }}>add</span>문구 추가</button></div>
      <div className="ph-info"><span className="ms" aria-hidden="true">format_quote</span><div><b>{PHRASE_RELEASE}</b> · {PHRASE_RELEASE_BY}<span>일탈 목록 초안과 질의서 초안을 만들 때 상황에 맞는 문구가 자동으로 들어갑니다. 중괄호 {'{ }'} 부분은 검토 값으로 바뀝니다.</span></div></div>
      <div className="ph-bar">
        <div className="seg" role="group" aria-label="구분">
          {KINDS.map(([k, label]) => (
            <button key={k} type="button" className={kind === k ? 'on' : ''} aria-pressed={kind === k} onClick={() => { setKind(k); setPage(1) }}>
              {label} <span className="ph-n">{vis.filter((r) => k === 'all' || r[1] === k).length}</span></button>
          ))}
        </div>
        <label className="ph-q"><span className="ms" aria-hidden="true">search</span><input placeholder="문구, 상황, 코드 찾기" aria-label="문구 찾기" value={q} onChange={(e) => { setQ(e.target.value); setPage(1) }} /></label>
        <label className="ph-ck"><input type="checkbox" checked={showOld} onChange={() => { setShowOld(!showOld); setPage(1) }} />폐기된 문구도 보기</label>
      </div>
      <div className="ph-box">
        <div className="ph-tr ph-th"><span>코드</span><span>구분</span><span>쓰는 상황과 문구</span><span>최근 90일 사용</span><span>최근 수정</span><span>상태</span><span /></div>
        {found.length === 0 && <div className="ph-empty">조건에 맞는 문구가 없습니다.</div>}
        {rows.map(([code, k, when, en, ko, rule, hist, used, by, date, st]) => {
          const o = !!open[code]
          return (
            <div key={code} className={'ph-it' + (o ? ' open' : '') + (st === 'old' ? ' old' : '')}>
              <button type="button" className="ph-tr ph-row" onClick={() => setOpen({ ...open, [code]: !o })} aria-expanded={o}>
                <span className="mono ph-code">{code}</span>
                <span className="ph-kind">{KIND_NAMES[k]}</span>
                <span className="ph-main"><b>{when}</b><span className="ell">{en}</span></span>
                <span className="mono">{st === 'rev' ? '—' : `${used}회`}</span>
                <span className="ph-mut">{by}<br /><span className="mono">{date}</span></span>
                <span><span className={STATES[st][1]}>{STATES[st][0]}</span></span>
                <span className="ms" aria-hidden="true" style={{ color: 'var(--c-disabled)' }}>{o ? 'expand_less' : 'expand_more'}</span>
              </button>
              {o && (
                <div className="ph-det">
                  <div className="ph-txt">
                    <div><h4>영문 (제출용)</h4><p><Segs text={en} /></p></div>
                    <div><h4>국문 (내부 확인용)</h4><p><Segs text={ko} /></p></div>
                  </div>
                  <div className="ph-side">
                    <dl><div><dt>연결된 판정 규칙</dt><dd>{rule}</dd></div><div><dt>변경 이력</dt><dd>{hist}</dd></div></dl>
                    <div className="ph-act">
                      <button type="button" className="bo" onClick={() => copy(code, en)}><span className="ms" aria-hidden="true" style={{ fontSize: 'var(--ic-s)' }}>content_copy</span>영문 복사</button>
                      <a className="bo" href={href('/rules')}><span className="ms" aria-hidden="true" style={{ fontSize: 'var(--ic-s)' }}>rule</span>규칙 보기</a>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>
      {found.length > 10 && <Pager total={found.length} page={page} size={size} shown={rows.length} onPage={setPage} onSize={(n) => { setSize(n); setPage(1) }} />}
      {toast && <div className="stt" role="status"><span className="ms" aria-hidden="true">check_circle</span>{toast}</div>}
    </main>
  )
}
