import { useCallback, useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { api, type RunListItem } from '../api'
import { ROLE_NAMES, STAGE_NAMES } from '../components/labels'
import { EXAMPLE_NOTICES, EXAMPLE_UNREAD } from '../examples/header'
import { GROUPS, HOME, SETTINGS, groupOf, type GroupKey, type MenuItem, type MenuKey } from './menu'
import { AnalysisProgress } from './AnalysisProgress'
import { CrumbContext } from './crumb'
import { currentPath, href, useHashPath } from './router'
import { useSession } from './useSession'
import './shell.css'

// 앱 틀: 왼쪽 메뉴(aside.sb) + 머리글(header.hd) + 본문(.ws). 목업 v4.57 Main의 마크업·클래스 그대로 (SCR-00).

export type Crumb = { label: string; path?: string; tail?: boolean }

const MINI_KEY = 's2w.sbMini'

function readMini(): boolean {
  try { return localStorage.getItem(MINI_KEY) === '1' } catch { return false }
}

function Icon({ name, style }: { name: string; style?: CSSProperties }) {
  return <span className="ms" aria-hidden="true" style={style}>{name}</span>
}

function NavLink({ item, active }: { item: MenuItem; active: MenuKey }) {
  const on = item.key === active
  return (
    <a className={on ? 'on' : undefined} aria-current={on ? 'page' : undefined} href={href(item.path)} title={item.label}>
      <Icon name={item.icon} /><span className="t">{item.label}</span>
    </a>
  )
}

function SideNav({ active }: { active: MenuKey }) {
  const has = groupOf(active)
  // 목업처럼 한 묶음만 펼친다. 처음에는 지금 화면이 든 묶음을 펼친다(홈·설정처럼 묶음이 없으면 모두 접는다).
  // 다른 화면으로 옮기면 그 화면이 든 묶음을 펼친다.
  const [st, setSt] = useState<{ at: MenuKey; open: GroupKey | null }>({ at: active, open: has ?? null })
  const open = st.at === active ? st.open : (has ?? st.open)
  const setOpen = (g: GroupKey | null) => setSt({ at: active, open: g })
  return (
    <aside className="sb" id="sbnav" aria-label="주 메뉴">
      <div className="sbfx" aria-hidden="true"><i className="au a1" /><i className="au a2" /><i className="au a3" /></div>
      <div className="sb-brand">
        <a className="sb-plate" href={href('/')} aria-label="홈으로">
          <img className="sb-ls" src="/img/spec2win-white.png" alt="Spec2Win" width={131} height={26} />
        </a>
        <div className="sb-prod"><span>RFP 기술 검토 지원 시스템</span></div>
      </div>
      <nav className="sb-nav" aria-label="메뉴">
        <NavLink item={HOME} active={active} />
        {GROUPS.map((g) => (
          <div key={g.key} style={{ display: 'contents' }}>
            <button type="button" className={'sb-g' + (has === g.key ? ' has' : '')} aria-expanded={open === g.key}
              aria-controls={`sbk-${g.key}`} onClick={() => setOpen(open === g.key ? null : g.key)}>
              <Icon name={g.icon} /><span className="t">{g.label}</span><span className="ms sb-car" aria-hidden="true">expand_more</span>
            </button>
            <div className={'sb-kids' + (open === g.key ? ' open' : '')} id={`sbk-${g.key}`}>
              {g.items.map((i) => <NavLink key={i.key} item={i} active={active} />)}
            </div>
          </div>
        ))}
        <div className="sbdots" aria-hidden="true"><i className="b" /><i className="w w1" /><i className="w w2" /><i className="w w3" /></div>
      </nav>
      <div className="sb-foot">
        <a className={'sb-link' + (active === 'settings' ? ' on' : '')} href={href(SETTINGS.path)} title={SETTINGS.label}>
          <Icon name={SETTINGS.icon} /><span className="t">{SETTINGS.label}</span>
        </a>
      </div>
    </aside>
  )
}

/** 찾은 글자를 <mark>로 감싼다 (목업 검색 결과 모양). */
function Hit({ text, q }: { text: string; q: string }) {
  const i = text.toLowerCase().indexOf(q.toLowerCase())
  if (i < 0) return <>{text}</>
  return <>{text.slice(0, i)}<mark>{text.slice(i, i + q.length)}</mark>{text.slice(i + q.length)}</>
}

function runTitle(r: RunListItem): string {
  return r.files ?? `검토 #${r.run_id}`
}

function GlobalSearch({ open, onOpen, onClose }: { open: boolean; onOpen: () => void; onClose: () => void }) {
  const [q, setQ] = useState('')
  const [runs, setRuns] = useState<RunListItem[] | null>(null)
  const input = useRef<HTMLInputElement>(null)
  useEffect(() => {
    if (open && runs === null) api.runs().then(setRuns, () => setRuns([]))
  }, [open, runs])
  const query = q.trim()
  const hits = !query || !runs ? [] : runs.filter((r) =>
    String(r.run_id) === query.replace(/^#/, '') || runTitle(r).toLowerCase().includes(query.toLowerCase()))
  const go = () => { onOpen(); if (!query) input.current?.focus() }
  return (
    <div className="gsw">
      <label className="search">
        <Icon name="search" style={{ fontSize: 'var(--ic-s)' }} />
        <input ref={input} aria-label="검토, 요구사항, 제품, 입찰 검색" placeholder="검토, 요구사항, 제품, 입찰 검색" value={q}
          onChange={(e) => { setQ(e.target.value); onOpen() }} onFocus={onOpen}
          onKeyDown={(e) => { if (e.key === 'Escape') onClose(); if (e.key === 'Enter') onOpen() }} />
      </label>
      <button type="button" className="gsb" onClick={go}>검색</button>
      {open && (
        <div className="gsp" role="listbox" aria-label="검색 결과">
          {hits.length === 0 && (
            <div className="gse">{query ? `"${query}"에 맞는 결과가 없습니다`
              : '검토 번호나 RFP 파일 이름으로 찾습니다. 요구사항·제품·입찰 찾기는 아직 없습니다.'}</div>
          )}
          {hits.length > 0 && (
            <div className="gsg">
              <h4>검토 {hits.length}</h4>
              {hits.slice(0, 4).map((r) => (
                <a key={r.run_id} className="gsi" href={href(`/reviews/${r.run_id}`)} onClick={onClose}>
                  <Icon name="fact_check" />
                  <span className="tx"><b><Hit text={runTitle(r)} q={query} /></b>
                    <span>#{r.run_id} · {STAGE_NAMES[r.stage] ?? r.stage} · {r.started_at.slice(0, 16).replace('T', ' ')}</span></span>
                </a>
              ))}
            </div>
          )}
          {query && runs && <div className="gsf">검토 {runs.length} 중에서 찾았습니다</div>}
        </div>
      )}
    </div>
  )
}

function Notices({ open, onToggle, onClose }: { open: boolean; onToggle: () => void; onClose: () => void }) {
  const [read, setRead] = useState<Record<string, boolean>>({})
  const [allRead, setAllRead] = useState(false)
  const unread = allRead ? 0 : EXAMPLE_NOTICES.slice(0, EXAMPLE_UNREAD).filter((n) => !read[n.id]).length
  return (
    <div className="ntw">
      <button type="button" className="tl nt" aria-label={`알림 ${unread}건`} title="알림" onClick={onToggle} aria-expanded={open}>
        <Icon name="notifications" />{unread > 0 && <span className="ndot">{unread}</span>}
      </button>
      {open && (
        <div className="ntp" role="dialog" aria-label="알림">
          <div className="nth"><b>알림 <span className="smp" title="알림 기능이 아직 없어 예시를 보여 줍니다">예시</span></b>
            <button type="button" onClick={() => setAllRead(true)}>모두 읽음으로</button></div>
          {EXAMPLE_NOTICES.map((n, i) => {
            const un = i < EXAMPLE_UNREAD && !allRead && !read[n.id]
            return (
              <a key={n.id} className={'nti' + (un ? ' un' : '')} href={href(n.path)}
                onClick={() => { setRead({ ...read, [n.id]: true }); onClose() }}>
                <span className={'ic ' + n.tone}><Icon name={n.icon} /></span>
                <span className="tx"><b>{n.title}</b><span>{n.sub}</span></span><span className="t">{n.t}</span>
              </a>
            )
          })}
          <a className="ntf" href={href('/settings')} onClick={onClose}>알림 설정</a>
        </div>
      )}
    </div>
  )
}

/** 아바타 글자: 이름 마지막 낱말의 첫 글자 ("기본 승인자" → 승). 목업은 사진 (SCR-00_공유.md). */
function initial(name: string): string {
  return name.trim().split(/\s+/).pop()?.slice(0, 1) ?? '?'
}

function useOnline(): boolean {
  const [on, setOn] = useState(() => navigator.onLine !== false)
  useEffect(() => {
    const up = () => setOn(true)
    const down = () => setOn(false)
    window.addEventListener('online', up)
    window.addEventListener('offline', down)
    return () => { window.removeEventListener('online', up); window.removeEventListener('offline', down) }
  }, [])
  return on
}

/** 머리글 오른쪽 사용자. 로그인이 없으므로 누르면 사용자를 바꾼다 (목업은 로그인 화면으로 감, SCR-00_공유.md). */
function UserChip({ open, onToggle, onClose }: { open: boolean; onToggle: () => void; onClose: () => void }) {
  const { user, users, setUserId } = useSession()
  const online = useOnline()
  const state = online ? '온라인' : '오프라인'
  const role = user ? ROLE_NAMES[user.role] ?? user.role : ''
  return (
    <div className="ntw">
      <button type="button" className="user" aria-label="사용자 바꾸기" aria-expanded={open} onClick={onToggle}
        title={user ? `${user.user_name} · ${state} · 사용자 바꾸기` : '사용자 없음'}>
        <span className="av" aria-hidden="true">{user ? initial(user.user_name) : '?'}<i className={online ? 'on' : 'off'} /></span>
        <span className="sr">{state}</span>
        <span className="uw"><b>{user?.user_name ?? '사용자 없음'}</b><span>{role}</span></span>
      </button>
      {open && (
        <div className="ntp" role="dialog" aria-label="사용자 바꾸기">
          <div className="nth"><b>사용자 바꾸기</b></div>
          {users.map((u) => (
            <button key={u.user_id} type="button" className={'nti' + (u.user_id === user?.user_id ? ' un' : '')}
              aria-pressed={u.user_id === user?.user_id} onClick={() => { setUserId(u.user_id); onClose() }}>
              <span className="ic c-blue">{initial(u.user_name)}</span>
              <span className="tx"><b>{u.user_name}</b><span>{ROLE_NAMES[u.role] ?? u.role}</span></span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

type Pop = 'search' | 'progress' | 'notice' | 'user' | null

function Header({ crumbs, mini, onToggleMini }: { crumbs: Crumb[]; mini: boolean; onToggleMini: () => void }) {
  const [pop, setPop] = useState<Pop>(null)
  const close = useCallback(() => setPop(null), [])
  const label = mini ? '메뉴 펼치기' : '메뉴 접기'
  return (
    <>
      {pop && <div className="hdbk" onClick={close} />}
      <header className="hd">
        <button type="button" className="tl sbt" onClick={onToggleMini} aria-label={label} aria-expanded={!mini}
          aria-controls="sbnav" title={label}><Icon name={mini ? 'menu' : 'menu_open'} /></button>
        <nav className="crumb" aria-label="현재 위치">
          {crumbs.map((c, i) => (
            <span key={i} style={{ display: 'contents' }}>
              {i > 0 && <Icon name="chevron_right" />}
              {i === crumbs.length - 1 ? <b>{c.label}</b> : <a href={href(c.path ?? '/')}>{c.label}</a>}
            </span>
          ))}
        </nav>
        <GlobalSearch open={pop === 'search'} onOpen={() => setPop('search')} onClose={close} />
        <AnalysisProgress open={pop === 'progress'} onToggle={() => setPop(pop === 'progress' ? null : 'progress')} onClose={close} />
        <button type="button" className="tl" aria-label="도움말" title="도움말"><Icon name="help" /></button>
        <Notices open={pop === 'notice'} onToggle={() => setPop(pop === 'notice' ? null : 'notice')} onClose={close} />
        <UserChip open={pop === 'user'} onToggle={() => setPop(pop === 'user' ? null : 'user')} onClose={close} />
      </header>
    </>
  )
}

/** 화면 하나. active는 왼쪽 메뉴에서 켤 항목, crumbs는 머리글 위치 (마지막이 지금 화면). */
export function Shell({ active, crumbs, children }: { active: MenuKey; crumbs: Crumb[]; children: ReactNode }) {
  const [mini, setMini] = useState(readMini)
  const path = useHashPath()
  const [tail, setTail] = useState<{ path: string; label: string | null }>({ path, label: null })
  // 화면이 알려 준 이름은 tail 표시가 있는 칸, 없으면 마지막 칸에 넣는다
  const marked = crumbs.findIndex((c) => c.tail)
  const at = marked >= 0 ? marked : crumbs.length - 1
  const shown = tail.label && tail.path === path
    ? crumbs.map((c, i) => (i === at ? { ...c, label: tail.label! } : c)) : crumbs
  const setLabel = useCallback((label: string | null) => setTail({ path: currentPath(), label }), [])
  const toggle = () => {
    const v = !mini
    try { localStorage.setItem(MINI_KEY, v ? '1' : '0') } catch { /* 기억하지 못해도 접기는 된다 */ }
    setMini(v)
  }
  return (
    <div className={'app fs-s' + (mini ? ' mini' : '')}>
      <SideNav active={active} />
      <div className="wk">
        <Header crumbs={shown} mini={mini} onToggleMini={toggle} />
        <CrumbContext.Provider value={setLabel}><div className="ws">{children}</div></CrumbContext.Provider>
      </div>
    </div>
  )
}
