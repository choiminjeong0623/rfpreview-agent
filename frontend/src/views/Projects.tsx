import { useState } from 'react'
import { api, type BusinessListItem } from '../api'
import { BUSINESS_ROLE_NAMES, RANGE_CHIP, RANGE_NAMES, ddCls, ddText } from '../components/business'
import { dueText } from '../components/format'
import { useLoad, useRepeat } from '../components/useLoad'
import { usePageCss } from '../shell/pageCss'
import { href } from '../shell/router'
import { useSession } from '../shell/useSession'

// SCR-04 사업 현황 (목업 v4.57 Projects). docs/screens/SCR-04-사업현황.md
// 사업(입찰 한 건)에 연결된 검토들의 범위별 상태를 보여 준다 (add-project-status). 상태는 서버가 계산한다.
// "내 사업"은 머리글에서 고른 사용자 기준. "등록 전 범위" 칸은 만들지 않았다 (SCR-04_공유.md).
// v4.96: 요약 칸 설명 줄과 누르면 거르기 (update-home-projects design.md 5). 조건은 서버 요약과 같다.

type Filter = { st: 'open' | 'done' | 'all'; cty: string; due: '' | '3' | '7'; qf: 'all' | 'name' | 'cust' | 'tender'; q: string }
const START: Filter = { st: 'open', cty: '', due: '', qf: 'all', q: '' }
const SCOPES: ['mine' | 'all', string][] = [['mine', '내 사업'], ['all', '팀 전체']]
const DUE: [Filter['due'], string][] = [['', '전체'], ['3', '3일 안'], ['7', '7일 안']]

function match(b: BusinessListItem, f: Filter) {
  const q = f.q.trim().toLowerCase()
  const name = b.business_name
  const cust = b.customer_name ?? ''
  const tender = b.tender_no ?? ''
  const text = { all: name + cust + tender, name, cust, tender }[f.qf]
  const done = b.submitted_at !== null
  return (f.st === 'all' || (f.st === 'done' ? done : !done)) && (!f.cty || b.country === f.cty)
    && (!f.due || (b.days_left !== null && b.days_left >= 0 && b.days_left <= Number(f.due))) && (!q || text.toLowerCase().includes(q))
}

type Quick = 'open' | 'due3' | 'over'
const QUICK: [Quick, string][] = [['open', '진행 중 사업'], ['due3', '3일 내 제출 마감'], ['over', '마감 지남']]
const QUICK_TEST: Record<Quick, (b: BusinessListItem) => boolean> = {
  open: (b) => b.submitted_at === null,
  due3: (b) => b.submitted_at === null && b.days_left !== null && b.days_left >= 0 && b.days_left <= 3,
  over: (b) => b.submitted_at === null && b.days_left !== null && b.days_left < 0,
}

/** 요약 칸 설명 줄: 진행 중 "설비 범위 n개 · 내 담당 m개", 3일 내 "이름 D-n · 이름 D-n 외 k", 마감 지남 "없음" 또는 이름 */
function quickSub(k: Quick, list: BusinessListItem[], me: number | null): string {
  if (k === 'open') {
    const ranges = list.flatMap((b) => b.ranges)
    return `설비 범위 ${ranges.length}개 · 내 담당 ${ranges.filter((r) => me !== null && r.engineer_id === me).length}개`
  }
  if (!list.length) return '없음'
  const sorted = [...list].sort((a, b) => dueOrder(a) - dueOrder(b))
  const shown = sorted.slice(0, k === 'due3' ? 2 : 1).map((b) => k === 'due3' ? `${b.business_name} ${ddText(b)}` : b.business_name)
  return shown.join(' · ') + (sorted.length > shown.length ? ` 외 ${sorted.length - shown.length}` : '')
}

// 마감 가까운 순, 마감이 없으면 뒤로
const dueOrder = (b: BusinessListItem) => b.days_left ?? Number.MAX_SAFE_INTEGER

export function Projects() {
  usePageCss('Projects')
  usePageCss('ProjectsV496')
  const { user } = useSession()
  const [scope, setScope] = useState<'mine' | 'all'>('mine')
  // 검색 칸은 고친 값(draft)과 적용한 값(applied)을 따로 둔다. 검색 단추나 Enter로 적용 (목업과 같음)
  const [draft, setDraft] = useState<Filter>(START)
  const [applied, setApplied] = useState<Filter>(START)
  const [quick, setQuick] = useState<Quick | null>(null)
  const mine = scope === 'mine' && user !== null
  const list = useLoad(() => api.businesses(user?.user_id ?? null, mine ? 'mine' : 'all'), [user?.user_id, mine])
  // 처리 중인 검토가 있으면 5초마다 다시 본다
  useRepeat(!!list.data?.items.some((b) => b.ranges.some((r) => r.state === 'an')), list.reload)
  const base = list.data?.items ?? []
  const countries = [...new Set(base.map((b) => b.country).filter((c): c is string => !!c))]
  // 요약 칸으로 거를 때는 상태 칸(진행 중·제출 완료)을 보지 않는다. 요약 칸 조건이 이미 "제출 안 함"이다
  const rows = base.filter((b) => (quick ? QUICK_TEST[quick](b) && match(b, { ...applied, st: 'all' }) : match(b, applied)))
    .sort((a, b) => dueOrder(a) - dueOrder(b))
  const set = (part: Partial<Filter>) => setDraft({ ...draft, ...part })
  const sum = list.data?.summary

  return (
    <main className="main">
      <div className="ttl"><h1>사업 현황</h1><a className="bp" href={href('/register')}><span className="ms" aria-hidden="true" style={{ fontSize: 'var(--ic-s)' }}>add</span>RFP 등록</a></div>
      <div className="sh-sum qk" role="group" aria-label="사업 요약 · 누르면 아래 목록을 거릅니다" style={{ gridTemplateColumns: 'repeat(3, minmax(0, 1fr))' }}>
        {QUICK.map(([k, label]) => {
          const n = sum ? sum[k === 'over' ? 'overdue' : k] : null
          const on = quick === k
          return (
            <button key={k} type="button" className={on ? 'on' : ''} aria-pressed={on} disabled={!n && !on}
              title={on ? '다시 누르면 모두 보기' : '누르면 아래 목록을 이 조건으로 거름'} onClick={() => setQuick(on ? null : k)}>
              <span className="ql">{label}<b className={n && k !== 'open' ? 'c-red' : ''}>{n ?? '—'}</b></span>
              <span className="qs">{list.data ? quickSub(k, base.filter(QUICK_TEST[k]), user?.user_id ?? null) : ''}</span>
            </button>
          )
        })}
      </div>
      <section className="sec">
        <div className="sech"><h2>사업 <span style={{ fontWeight: 400, color: 'var(--c-muted)' }}>{rows.length}</span></h2>
          <div className="seg" role="group" aria-label="범위">
            {SCOPES.map(([k, label]) => <button key={k} type="button" className={scope === k ? 'on' : ''} aria-pressed={scope === k} onClick={() => setScope(k)}>{label}</button>)}
          </div>
        </div>
        {/* 검색 조건: 1줄 왼쪽 제출 마감(아래 -전체-와 같은 시작선), 오른쪽 상태·국가 (minjeong 10-30) */}
        <div className="sp" role="search" aria-label="사업 찾기">
          <div className="sp-r1">
            <div className="sp-f" role="radiogroup" aria-label="제출 마감"><span className="sp-l">제출 마감</span>
              {DUE.map(([k, label]) => <label key={k} className="sp-rd"><input type="radio" name="due" checked={draft.due === k} onChange={() => set({ due: k })} />{label}</label>)}</div>
            <div className="sp-f" style={{ marginLeft: 'auto', gap: 32 }}>
              <label className="sp-f"><span className="sp-l">상태</span>
                <select className="fi" value={draft.st} onChange={(e) => set({ st: e.target.value as Filter['st'] })}>
                  <option value="open">진행 중</option><option value="done">제출 완료</option><option value="all">전체</option></select></label>
              <label className="sp-f"><span className="sp-l">국가</span>
                <select className="fi" value={draft.cty} onChange={(e) => set({ cty: e.target.value })}>
                  <option value="">모든 국가</option>{countries.map((c) => <option key={c}>{c}</option>)}</select></label>
            </div>
          </div>
          <div className="sp-r2">
            <select className="fi sp-qf" value={draft.qf} onChange={(e) => set({ qf: e.target.value as Filter['qf'] })} aria-label="검색 대상">
              <option value="all">-전체-</option><option value="name">사업명</option><option value="cust">고객사</option><option value="tender">입찰 번호</option></select>
            <input className="fi sp-q" value={draft.q} onChange={(e) => set({ q: e.target.value })} onKeyDown={(e) => { if (e.key === 'Enter') setApplied(draft) }}
              placeholder="사업명, 고객사, 고객 입찰 번호" aria-label="검색어" />
            <button type="button" className="bo" onClick={() => { setDraft(START); setApplied(START) }}>초기화</button>
            <button type="button" className="bp" onClick={() => setApplied(draft)}><span className="ms" aria-hidden="true" style={{ fontSize: 'var(--ic-s)' }}>search</span>검색</button>
          </div>
        </div>
        {quick && (
          <div className="qkbar"><span className="ms" aria-hidden="true">filter_alt</span>
            <span><b>{QUICK.find(([k]) => k === quick)![1]} {rows.length}건</b>만 보는 중</span>
            <button type="button" className="lnk" onClick={() => setQuick(null)}>모두 보기</button></div>
        )}
        {list.error && <div className="sh-empty" role="alert">사업 목록을 불러오지 못했습니다: {list.error}</div>}
        <div className="sh-box" style={{ marginTop: 16 }}>
          <div className="pl-tr sh-th"><span>순번</span><span>사업명</span><span>고객사 · 국가</span><span>고객 입찰 번호</span><span>제출 마감</span><span>설비 범위별 진행</span><span>내 역할</span><span>영업</span><span /></div>
          {list.data && rows.length === 0 && (
            <div className="sh-empty">{base.length === 0 && mine ? '내가 관여한 사업이 없습니다. "팀 전체"를 눌러 보세요.' : '조건에 맞는 사업이 없습니다.'}</div>
          )}
          {!list.data && !list.error && <div className="sh-empty">불러오는 중…</div>}
          {rows.map((b, i) => (
            <a key={b.business_id} className="pl-tr pl-row" href={href(`/projects/${b.business_no}`)}>
              <span className="mono sh-mut" style={{ textAlign: 'right' }}>{i + 1}</span>
              <span className="pl-nm"><b>{b.business_name}</b><span className="ell mono">{b.business_no}</span></span>
              <span className="pl-nm"><span style={{ color: 'var(--c-text)' }}>{b.customer_name ?? '—'}</span><span>{b.country ?? ''}</span></span>
              <span className="mono sh-mut">{b.tender_no ?? '—'}</span>
              <span><span className={'dd ' + ddCls(b)}>{ddText(b)}</span><span className="mono sh-mut" style={{ display: 'block' }}>{b.due_date ? dueText(b.due_date) : ''}</span></span>
              <span className="pl-rg">
                {b.ranges.length === 0 && <span className="sh-mut">연결된 검토 없음</span>}
                {b.ranges.map((r) => (
                  <span key={r.run_id} className={`pj-ch ${RANGE_CHIP[r.state]}`}
                    title={`${r.review_name ?? r.review_no} · ${r.engineer_name ?? '담당 없음'}${r.open_requests ? ` · 협조 미확인 ${r.open_requests}건` : ''}`}>
                    {RANGE_NAMES[r.state]}</span>
                ))}</span>
              <span className="sh-mut" style={{ color: 'var(--c-text)' }}>{b.my_role ? BUSINESS_ROLE_NAMES[b.my_role] : '—'}</span>
              <span className="sh-mut">{b.sales_name ?? '—'}</span>
              <span className="ms" aria-hidden="true" style={{ color: 'var(--c-disabled)' }}>chevron_right</span>
            </a>
          ))}
        </div>
      </section>
    </main>
  )
}
