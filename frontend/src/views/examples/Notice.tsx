import { useState } from 'react'
import { EXAMPLE_POSTS } from '../../examples/SCR-21'
import { usePageCss } from '../../shell/pageCss'
import { ExampleBand } from '../detail/ExampleTab'

// SCR-21 공지사항 (목업 v4.57 Notice). docs/screens/SCR-21-공지사항.md
// 게시판 API가 없어 예시 데이터로만 보여 준다. 읽음 표시와 조회 수는 화면 안에서만 바뀐다.

export function Notice() {
  usePageCss('Notice')
  const [mustOnly, setMustOnly] = useState(false)
  const [q, setQ] = useState('')
  const [open, setOpen] = useState<Record<number, boolean>>({})
  const [read, setRead] = useState<Record<number, boolean>>({})
  const needle = q.trim().toLowerCase()
  const rows = EXAMPLE_POSTS.map((p, i) => [p, i] as const)
    .filter(([p]) => (!mustOnly || p[0] === 'must') && (!needle || (p[1] + p[2] + p[5]).toLowerCase().includes(needle)))

  return (
    <main className="main">
      <ExampleBand />
      <div className="ttl"><h1>공지사항</h1>
        <span title="글쓰기는 팀장과 지정 담당자만 할 수 있습니다"><button type="button" className="bp" disabled><span className="ms" aria-hidden="true" style={{ fontSize: 'var(--ic-s)' }}>edit</span>글쓰기</button></span></div>
      <div className="sh-note"><span className="ms" aria-hidden="true">info</span><span>팀 공지입니다. 글쓰기는 팀장과 지정 담당자만 할 수 있고, 팀원은 모두 읽을 수 있습니다.</span></div>
      <div className="sh-bar">
        <label className="sh-ck"><input type="checkbox" checked={mustOnly} onChange={() => setMustOnly(!mustOnly)} />필독만 보기</label>
        <label className="sh-q"><span className="ms" aria-hidden="true">search</span><input placeholder="제목, 내용, 작성자 찾기" aria-label="글 찾기" value={q} onChange={(e) => setQ(e.target.value)} /></label>
        <span className="sh-mut" style={{ marginLeft: 'auto' }}>{rows.length}건</span>
      </div>
      <div className="sh-box">
        <div className="bp-tr sh-th"><span>구분</span><span>제목</span><span>작성자</span><span>날짜</span><span>조회</span><span /></div>
        {rows.length === 0 && <div className="sh-empty">조건에 맞는 글이 없습니다.</div>}
        {rows.map(([[kind, title, by, date, views, body, isNew], i]) => {
          const o = !!open[i]
          return (
            <div key={i} className="bp-it">
              <button type="button" className="bp-tr bp-row" aria-expanded={o} onClick={() => { setOpen({ ...open, [i]: !o }); setRead({ ...read, [i]: true }) }}>
                <span><span className={kind === 'must' ? 'st c-red' : 'st c-grey'}>{kind === 'must' ? '필독' : '일반'}</span></span>
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
