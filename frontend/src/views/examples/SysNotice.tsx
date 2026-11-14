import { useState } from 'react'
import { EXAMPLE_SYS_POSTS, type SysPost } from '../../examples/SCR-22'
import { usePageCss } from '../../shell/pageCss'
import { ExampleBand } from '../detail/ExampleTab'

// SCR-22 시스템 공지 (목업 v4.57 SysNotice). docs/screens/SCR-22-시스템공지.md
// 시스템 공지 API가 없어 예시 데이터로만 보여 준다. 읽음 표시와 조회 수는 화면 안에서만 바뀐다.

const KINDS: ['all' | SysPost[0], string][] = [['all', '전체'], ['chk', '점검'], ['upd', '업데이트'], ['err', '장애']]
const TAGS: Record<SysPost[0], [string, string]> = { chk: ['점검', 'st c-grey'], upd: ['업데이트', 'st c-blue'], err: ['장애', 'st c-red'] }

export function SysNotice() {
  usePageCss('SysNotice')
  const [kind, setKind] = useState<'all' | SysPost[0]>('all')
  const [q, setQ] = useState('')
  const [open, setOpen] = useState<Record<number, boolean>>({})
  const [read, setRead] = useState<Record<number, boolean>>({})
  const needle = q.trim().toLowerCase()
  const rows = EXAMPLE_SYS_POSTS.map((p, i) => [p, i] as const)
    .filter(([p]) => (kind === 'all' || p[0] === kind) && (!needle || (p[1] + p[2] + p[5]).toLowerCase().includes(needle)))

  return (
    <main className="main">
      <ExampleBand />
      <div className="ttl"><h1>시스템 공지</h1>
        <span title="시스템 관리자만 쓸 수 있습니다"><button type="button" className="bp" disabled><span className="ms" aria-hidden="true" style={{ fontSize: 'var(--ic-s)' }}>edit</span>글쓰기</button></span></div>
      <div className="sh-note"><span className="ms" aria-hidden="true">info</span><span>Spec2Win 점검·업데이트·장애 안내입니다. 시스템 관리자만 쓸 수 있습니다.</span></div>
      <div className="sh-bar">
        <div className="seg" role="group" aria-label="종류">
          {KINDS.map(([k, label]) => <button key={k} type="button" className={kind === k ? 'on' : ''} aria-pressed={kind === k} onClick={() => setKind(k)}>{label}</button>)}
        </div>
        <label className="sh-q"><span className="ms" aria-hidden="true">search</span><input placeholder="제목, 내용, 작성자 찾기" aria-label="글 찾기" value={q} onChange={(e) => setQ(e.target.value)} /></label>
        <span className="sh-mut" style={{ marginLeft: 'auto' }}>{rows.length}건</span>
      </div>
      <div className="sh-box">
        <div className="bp-tr sh-th"><span>구분</span><span>제목</span><span>작성자</span><span>날짜</span><span>조회</span><span /></div>
        {rows.length === 0 && <div className="sh-empty">조건에 맞는 글이 없습니다.</div>}
        {rows.map(([[k, title, by, date, views, body, isNew], i]) => {
          const o = !!open[i]
          return (
            <div key={i} className="bp-it">
              <button type="button" className="bp-tr bp-row" aria-expanded={o} onClick={() => { setOpen({ ...open, [i]: !o }); setRead({ ...read, [i]: true }) }}>
                <span><span className={TAGS[k][1]}>{TAGS[k][0]}</span></span>
                <span className="bp-t"><b className="ell">{title}</b>{isNew && !read[i] && <i className="sh-new" title="읽지 않음" />}</span>
                <span className="sh-mut">{by}</span><span className="mono sh-mut">{date}</span><span className="mono sh-mut">{views + (read[i] ? 1 : 0)}</span>
                <span className="ms" aria-hidden="true" style={{ color: 'var(--c-disabled)' }}>{o ? 'expand_less' : 'expand_more'}</span>
              </button>
              {o && <div className="bp-body">{body}</div>}
            </div>
          )
        })}
      </div>
    </main>
  )
}
