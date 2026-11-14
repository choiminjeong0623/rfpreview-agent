import { useCallback, useState } from 'react'
import { api, type Assignment, type RunListItem, type User } from '../api'
import { daysLeft, dday, dueText, isoDay, reviewTitle, stamp } from '../components/format'
import { progress } from '../components/progress'
import { ROLE_NAMES, STAGE_NAMES, STAGE_TONES, STEP_NAMES } from '../components/labels'
import { before, byDue, myTurn } from '../components/myWork'
import { SummaryBox } from '../components/SummaryBox'
import { useLoad, useRepeat } from '../components/useLoad'
import { EVENTS, FILES, NOTICES, SYS_NOTICES } from '../examples/SCR-03'
import { href } from '../shell/router'
import { usePageCss } from '../shell/pageCss'
import { useSession } from '../shell/useSession'
import { Button, useToast } from '../ui'
import { ExampleBand } from './detail/ExampleTab'
import { revisionText } from '../components/revision'
import './detail.css'

// SCR-03 홈 (목업 v4.96 Home). docs/screens/SCR-03-홈.md "v4.96 바뀐 점", change update-home-projects
// 나의 업무 세 칸, 오늘 할 일, 나의 검토 일정(일정·단계별·사업별), 어제 이후 바뀐 것, 분석 실패 알림, 팀 업무는 실제 데이터.
// 공지·시스템 공지·자료실·행사는 게시판 API가 없어 예시 (SCR-03_공유.md). 요약 상자는 9단계(add-screen-summary).

type Col = 'an' | 'chk' | 'co' | 'ap' | 'sub'
type Filter = 'mine' | 'wait' | 'soon'
type View = 'tl' | 'stage' | 'pj'
const COLS: [Col, string, string][] = [['an', '분석 중', 'bd-dot'], ['chk', '판정 확인', 'bd-dot b'], ['co', '협조 대기', 'bd-dot o'], ['ap', '결재 대기', 'bd-dot n'], ['sub', '제출 준비', 'bd-dot g']]
const COL_CHIPS: Record<Col, string> = { an: 'st c-grey', chk: 'st c-blue', co: 'st c-ora', ap: 'st c-grey', sub: 'st c-green' }
/** 나의 업무 세 칸 (v4.96: "마감 경과" 칸은 없앰) */
const METRICS: [Filter, string, string][] = [
  ['mine', '내가 처리할 건', '내 차례인 검토(판정 확인·반려·분석 실패, 내가 결재자인 결재 대기)'],
  ['wait', '결재 대기', '결재자 확인을 기다리는 검토'],
  ['soon', '3일 내 마감', '오늘부터 3일 안에 마감되는 검토'],
]
const DAY = 86_400_000
const WEEK = ['일', '월', '화', '수', '목', '금', '토']

/** 협조 요청: 검토마다 아직 확인하지 않은 요청 수와 24시간 넘은 수 */
type Pending = { n: number; late: number }

function pendingByRun(lists: Assignment[][], now: number): Map<number, Pending> {
  const out = new Map<number, Pending>()
  for (const a of lists.flat()) {
    if (a.status === 'DONE') continue           // 회신 받지 않은 요청 (안 보냄·메일 보냄)
    const p = out.get(a.run_id) ?? { n: 0, late: 0 }
    p.n += 1
    if (now - new Date(a.sent_at).getTime() > DAY) p.late += 1
    out.set(a.run_id, p)
  }
  return out
}

/** 검토 단계 → 카드 열. 협조 요청이 남은 담당자 확인 검토는 "협조 대기" */
function colOf(r: RunListItem, pending: Map<number, Pending>): Col {
  if (r.stage === 'PROCESSING' || r.stage === 'FAILED') return 'an'
  if (r.stage === 'APPROVAL') return 'ap'
  if (r.stage === 'APPROVED') return 'sub'
  if (r.stage === 'ENGINEER_REVIEW' && pending.get(r.run_id)?.n) return 'co'
  return 'chk'
}

function left(r: RunListItem): number | null {
  if (!r.due_date || r.stage === 'APPROVED') return null
  return daysLeft(r.due_date)
}

function filters(turn: (r: RunListItem) => boolean): Record<Filter, (r: RunListItem) => boolean> {
  return {
    mine: turn,
    wait: (r) => r.stage === 'APPROVAL',
    soon: (r) => { const n = left(r); return n !== null && n >= 0 && n <= 3 },
  }
}

/** 목업 마감 칩: 지났거나 오늘이면 진한 빨강, 3일 이하 빨강, 7일 이하 주황 */
function ddCls(n: number | null): string {
  if (n === null) return 'dd neu'
  return 'dd ' + (n <= 0 ? 'neg hard pill-n' : n <= 3 ? 'neg pill-n' : n <= 7 ? 'crit pill-c' : 'neu')
}

function card(r: RunListItem, col: Col, pending: Map<number, Pending>): { lines: string[]; note: string; tone: string } {
  const p = pending.get(r.run_id)
  const found = `일탈 후보 ${r.deviation_candidates}건 · 위험 조건 ${r.risks}건`
  switch (r.stage) {
    case 'PROCESSING': return { lines: [`${STEP_NAMES[r.step ?? ''] ?? '처리'} ${progress(r)} %`, '처리 중'], note: '', tone: '' }
    case 'FAILED': return { lines: [`${STEP_NAMES[r.failed_step ?? ''] ?? '처리'}에서 멈춤`], note: '분석 실패', tone: 'red' }
    case 'REJECTED': return { lines: [`요구사항 ${r.requirements}건`, found], note: '반려됨 · 다시 확인', tone: 'red' }
    case 'APPROVAL': return { lines: [found, '결재자 확인 중'], note: '', tone: '' }
    case 'APPROVED': return { lines: ['제출본 v1 확정', r.finished_at ? `처리 ${stamp(r.finished_at)}` : ''].filter(Boolean), note: '', tone: '' }
  }
  if (col === 'co' && p) {
    return { lines: [`요구사항 ${r.requirements}건`, `협조 미확인 ${p.n}건`], note: p.late ? '24시간 넘게 미확인' : '', tone: 'ora' }
  }
  return { lines: [`요구사항 ${r.requirements}건`, found], note: '', tone: '' }
}

export function Home() {
  usePageCss('Home')
  usePageCss('HomeV496')
  const { user, users } = useSession()
  const toast = useToast()
  const [now] = useState(() => Date.now())
  const runs = useLoad(() => api.runs(), [])
  useRepeat(!!runs.data?.some((r) => r.stage === 'PROCESSING'), runs.reload)   // 처리 중이면 5초마다 다시 본다
  const asg = useLoad(() => Promise.all(['COST', 'QUALITY', 'SALES'].map((r) => api.assignments(r))), [])
  const [filter, setFilter] = useState<Filter | null>(null)
  const [view, setView] = useState<View>('tl')
  const [closedFail, setClosedFail] = useState<number | null>(null)
  const [retrying, setRetrying] = useState<number | null>(null)
  const [retryError, setRetryError] = useState<{ id: number; text: string } | null>(null)

  const pending = pendingByRun(asg.data ?? [], now)
  const engineer = user?.role === 'ENGINEER'
  const dept = !!user && DEPTS.includes(user.role)
  const all = runs.data ?? []
  const board = engineer ? all.filter((r) => r.engineer_id === user!.user_id) : all
  const turn = myTurn(user)
  const FILTERS = filters(turn)
  const todo = all.filter(turn).sort(byDue)
  // 요약 상자 (add-screen-summary): 첫 문장의 수 = "내가 처리할 건" (같은 규칙·같은 최근 200건). 내 차례 수가 바뀌면 다시 쓴다
  const uid = user?.user_id ?? null
  const summary = useCallback(() => api.homeSummary(uid), [uid, todo.length]) // eslint-disable-line react-hooks/exhaustive-deps
  const failed = board.find((r) => r.stage === 'FAILED')
  const today = new Date(now)
  const dim = (r: RunListItem) => (filter && !FILTERS[filter](r) ? ' dim' : '')
  const sorted = [...board].sort((a, b) => (left(a) ?? 999) - (left(b) ?? 999))
  // 엔지니어가 결재자인 결재 대기는 내 보드에 없을 수 있어 강조·일정에도 넣는다
  const shown = engineer ? [...sorted, ...todo.filter((r) => !sorted.includes(r))] : sorted
  const deptOpen = dept ? (asg.data?.[DEPTS.indexOf(user!.role)] ?? []).filter((a) => a.status !== 'DONE').length : 0

  const retry = (r: RunListItem) => {
    if (retrying !== null) return
    setRetrying(r.run_id)
    setRetryError(null)
    api.retryRun(r.run_id, user?.user_id ?? null).then(() => {
      toast.done('다시 분석을 시작했습니다', { href: href(`/reviews/${r.run_id}`), label: '검토 열기' })
      runs.reload()
    }, (e: Error) => setRetryError({ id: r.run_id, text: e.message })).finally(() => setRetrying(null))
  }
  const retryBtn = (r: RunListItem, cls: string) => (
    <Button kind={cls === 'bp' ? 'primary' : 'secondary'} onClick={() => retry(r)} busy={retrying === r.run_id}
      disabledReason={engineer ? null : '엔지니어만 다시 시도할 수 있습니다'}>{retrying === r.run_id ? '시작하는 중…' : '재시도'}</Button>
  )

  const cardEl = (r: RunListItem, col: Col, byProject = false) => {
    const c = card(r, col, pending)
    const n = left(r)
    const fail = r.stage === 'FAILED' || r.stage === 'REJECTED'
    return (
      <a key={r.run_id} className={`bd-card${byProject ? ' bpc' : ''}${fail ? ' fail' : ''}${dim(r)}`} href={href(`/reviews/${r.run_id}`)}>
        <span className="bd-top"><span className="mono">{r.review_no}</span>
          {byProject ? <span className={COL_CHIPS[col]}>{COLS.find(([k]) => k === col)![1]}</span>
            : <span className={ddCls(n)}>{n === null ? (r.stage === 'APPROVED' ? '' : '마감 없음') : dday(r.due_date!).text}</span>}</span>
        <b className="bd-name">{byProject ? (r.review_name ?? reviewTitle(r)) : reviewTitle(r)}</b>
        {c.lines.map((l) => <span key={l} className="bd-line">{l}</span>)}
        {c.note && <span className={`bd-note ${c.tone}`}>{c.note}</span>}
      </a>
    )
  }

  const groups = [...new Map(sorted.map((r) => [r.project_name ?? '', [] as RunListItem[]])).entries()]
  for (const r of sorted) groups.find(([k]) => k === (r.project_name ?? ''))![1].push(r)
  const VIEWS: [View, string][] = [['tl', '일정'], ['stage', '단계별'], ['pj', '사업별']]

  return (
    <main className="main">
      {failed && closedFail !== failed.run_id && (
        <div className="banner" role="alert">
          <span className="ms neg" aria-hidden="true" style={{ marginTop: 2 }}>error</span>
          <div style={{ flex: '1 1 auto', minWidth: 0 }}><b>{failed.review_no} {reviewTitle(failed)} 분석이 멈췄습니다</b>{failed.error_message ?? '처리 중 오류가 났습니다.'}
            <dl className="fmeta">
              <div><dt>멈춘 단계</dt><dd>{STEP_NAMES[failed.failed_step ?? ''] ?? failed.failed_step ?? '—'}</dd></div>
              {failed.finished_at && <div><dt>발생</dt><dd>{stamp(failed.finished_at)}</dd></div>}
              <div><dt>자동 재시도</dt><dd>정해진 횟수 모두 실패</dd></div>
            </dl>
            <div className="facts">
              {retryBtn(failed, 'bp')}
              <a className="bo sm" href={href(`/reviews/${failed.run_id}`)}>오류 내용 보기</a>
              <span title="준비 중인 기능입니다"><button type="button" className="bo sm" disabled>규칙 기반으로 계속</button></span>
            </div>
            {retryError?.id === failed.run_id && <p className="c-red" style={{ margin: '6px 0 0' }}>{retryError.text}</p>}
          </div>
          <button type="button" className="bx" aria-label="알림 닫기" title="닫기" onClick={() => setClosedFail(failed.run_id)}><span className="ms" aria-hidden="true">close</span></button>
        </div>
      )}

      <div className="ttl">
        <h1 className="hero">홈</h1>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span className="range">오늘 {dueText(isoDay(today))} ({WEEK[today.getDay()]})</span>
          <a className="bp" href={href('/register')}><span className="ms" aria-hidden="true" style={{ fontSize: 'var(--ic-s)' }}>add</span>검토 등록</a>
        </div>
      </div>

      <div className="hm-sh"><h2>나의 업무</h2></div>
      <div className="qsum" role="group" aria-label="나의 업무 요약 · 누르면 아래 검토가 걸러집니다">
        {METRICS.map(([k, label, title]) => {
          const n = (k === 'mine' ? todo : shown.filter(FILTERS[k])).length
          const on = filter === k
          return (
            <button key={k} type="button" className={on ? 'on' : ''} aria-pressed={on} disabled={!!runs.data && !n && !on}
              title={`${title}${on ? ' · 다시 누르면 모두 보기' : ' · 누르면 아래 검토를 이 조건으로 거름'}`} onClick={() => setFilter(on ? null : k)}>
              <span className="ql">{label}</span><b className={n && k === 'soon' ? 'c-red' : ''}>{runs.data ? n : '—'}</b>
            </button>
          )
        })}
      </div>
      {engineer && (
        <p className="mlink"><a href={href('/reviews?scope=submitted')}>내가 올린 결재 목록에서 보기
          <span className="ms" aria-hidden="true">chevron_right</span></a></p>
      )}
      <SummaryBox load={summary} label="홈 요약" />

      {dept ? (
        <section className="td" aria-labelledby="tdTitle">
          <div className="td-h"><h2 id="tdTitle">오늘 할 일</h2><span>내 부서 협조 요청</span></div>
          <p className="bd-emp">내 부서 협조 요청 {asg.data ? deptOpen : '—'}건 <a className="lnk2" href={href('/todo')}>협조 요청에서 보기</a></p>
        </section>
      ) : (
        <TodayList list={todo} loaded={!!runs.data} engineer={engineer} retryBtn={retryBtn} retryError={retryError}
          onMore={() => { setFilter('mine'); setView('tl') }} />
      )}

      <section className="sec" aria-labelledby="dueTitle">
        <div className="sech">
          <h2 id="dueTitle">나의 검토 {VIEWS.find(([k]) => k === view)![1]} <span style={{ fontWeight: 400, color: 'var(--c-muted)' }}>{shown.length}건</span>
            {filter && <button type="button" className="fchip" onClick={() => setFilter(null)} aria-label="필터 해제">{METRICS.find(([k]) => k === filter)![1]}<span className="ms" aria-hidden="true">close</span></button>}</h2>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div className="seg" role="group" aria-label="보기 방식">
              {VIEWS.map(([k, label]) => <button key={k} type="button" className={view === k ? 'on' : ''} aria-pressed={view === k} onClick={() => setView(k)}>{label}</button>)}
            </div>
            <a className="ib" href={href('/reviews')} aria-label="검토 목록에서 모두 보기" title="검토 목록에서 모두 보기"><span className="ms" aria-hidden="true">more_horiz</span></a>
          </div>
        </div>
        {runs.error && <p role="alert">{runs.error} <button type="button" className="lnk" onClick={runs.reload}>다시 불러오기</button></p>}
        {view === 'tl' && <Week runs={(filter ? shown.filter(FILTERS[filter]) : shown)} turn={turn} now={now} />}
        {view === 'stage' && (
          <div className="bd">
            {COLS.map(([key, label, dot]) => {
              const cards = sorted.filter((r) => colOf(r, pending) === key)
              return (
                <div key={key} className="bd-col" aria-label={label}>
                  <div className="bd-ch"><span className={dot} /><b>{label}</b><span className="bd-n">{cards.length}</span></div>
                  {cards.slice(0, 8).map((r) => cardEl(r, key))}
                  {cards.length > 8 && <a className="bd-empty" href={href('/reviews')}>{cards.length - 8}건 더 · 검토 목록에서 보기</a>}
                  {!cards.length && <div className="bd-empty">없음</div>}
                </div>
              )
            })}
          </div>
        )}
        {view === 'pj' && (
          <div className="bpl">
            {groups.map(([name, rs]) => {
              const first = rs[0]
              const n = left(first)
              return (
                <div key={name || '-'} className="bpg">
                  <div className="bpg-h"><span className="bpg-n">{name || '사업 미지정'}</span>
                    {first.business_no && <a className="hm-mut" href={href(`/projects/${first.business_no}`)}>{first.business_no} · 사업 상세</a>}
                    <span className="hm-mut ell">{[first.customer_name, first.country].filter(Boolean).join(' · ')}</span>
                    {first.due_date && <><span className={ddCls(n)}>{dday(first.due_date).text}</span><span className="hm-mut">제출 마감 {dueText(first.due_date)}</span></>}</div>
                  <div className="bpg-c">{rs.map((r) => cardEl(r, colOf(r, pending), true))}</div>
                </div>
              )
            })}
          </div>
        )}
      </section>

      <Changes runs={board} now={now} />
      <TeamShare runs={all} users={users} pending={asg.data ?? []} />
      <Events />
    </main>
  )
}

const DEPTS = ['COST', 'QUALITY', 'SALES']

/** 오늘 할 일 (design.md 2): 내 차례인 검토 3건, 이유 한 줄, 단추. 확인 필요 줄 수는 보이는 3건만 부른다 */
function TodayList({ list, loaded, engineer, retryBtn, retryError, onMore }: {
  list: RunListItem[]; loaded: boolean; engineer: boolean
  retryBtn: (r: RunListItem, cls: string) => React.ReactNode; retryError: { id: number; text: string } | null; onMore: () => void
}) {
  const top = list.slice(0, 3)
  const ids = top.filter((r) => r.stage === 'ENGINEER_REVIEW' || r.stage === 'REJECTED').map((r) => r.run_id)
  const counts = useLoad(() => Promise.all(ids.map((id) => api.judgmentCounts(id).then((c) => [id, c.by_result.NEEDS_REVIEW ?? 0] as const))), [ids.join(',')])
  const review = new Map(counts.data ?? [])
  const [now] = useState(() => Date.now())
  const why = (r: RunListItem): { text: string; red: boolean } => {
    const due = r.due_date ? ` · 마감 ${dday(r.due_date).text}` : ''
    if (r.stage === 'FAILED') return { text: `${STEP_NAMES[r.failed_step ?? ''] ?? '처리'}에서 멈춤${due}`, red: true }
    if (r.stage === 'APPROVAL') {
      const days = r.requested_at ? Math.max(0, Math.floor((now - new Date(r.requested_at).getTime()) / DAY)) : 0
      return { text: `결재 대기 ${days}일째${due}`, red: false }
    }
    const parts: string[] = []
    if (r.stage === 'REJECTED') parts.push('반려됨')
    if (r.due_date) { const sb = before(r.due_date, 2); parts.push(`상신 권장 ${dueText(sb)} (${dday(sb).text})`) } else parts.push('마감 없음')
    const n = review.get(r.run_id)
    if (n !== undefined) parts.push(`확인 필요 ${n}건`)
    parts.push(`일탈 후보 ${r.deviation_candidates}`)
    return { text: parts.join(' · '), red: false }
  }
  return (
    <section className="td" aria-labelledby="tdTitle">
      <div className="td-h"><h2 id="tdTitle">오늘 할 일</h2><span>내 차례인 검토 · 상신 권장일이 빠른 순</span>
        {list.length > 3 && <button type="button" className="lnk2" onClick={onMore}>외 {list.length - 3}건 · 일정에서 보기</button>}</div>
      {loaded && !list.length && <p className="bd-emp">지금 내 차례인 검토가 없습니다.</p>}
      <ol className="td-l">
        {top.map((r, i) => {
          const w = why(r)
          const cls = i === 0 ? 'bp' : 'bo'
          return (
            <li key={r.run_id}><span className="no">{i + 1}</span>
              <span className="tx"><b>{r.review_no} {reviewTitle(r)}</b><span className={w.red ? 'red' : ''}>{w.text}</span>
                {retryError?.id === r.run_id && <span className="red">{retryError.text}</span>}</span>
              {r.stage === 'FAILED' && engineer ? retryBtn(r, cls)
                : <a className={cls} href={href(`/reviews/${r.run_id}`)}>{r.stage === 'APPROVAL' ? '결재 보기' : r.stage === 'FAILED' ? '오류 보기' : '판정 확인'}</a>}
            </li>
          )
        })}
      </ol>
    </section>
  )
}

type Ev = { run: RunListItem; sym: '제출 마감' | '상신 권장'; what: string; k: 'me' | 'ot' | 'sy' | 'fl'; hour: number }
const H0 = 8
const NH = 10
const TURN_NAMES = { me: '내 차례', ot: '다른 사람 차례', sy: '시스템 처리 중', fl: '분석 실패' }

/** 나의 검토 일정 (design.md 3): 7일 칸에 제출 마감과 상신 권장. 시각이 없어 상신 권장 09시 → 제출 마감 17시, 겹치면 한 시간씩 민다 */
function Week({ runs, turn, now }: { runs: RunListItem[]; turn: (r: RunListItem) => boolean; now: number }) {
  const [off, setOff] = useState(0)
  const base = new Date(now)
  const days = Array.from({ length: 7 }, (_, i) => new Date(base.getFullYear(), base.getMonth(), base.getDate() + off + i))
  const evs: Record<string, Ev[]> = {}
  const put = (day: string, e: Ev) => { (evs[day] ??= []).push(e) }
  for (const r of runs) {
    if (!r.due_date || r.stage === 'APPROVED') continue
    const k = r.stage === 'FAILED' ? 'fl' : r.stage === 'PROCESSING' ? 'sy' : turn(r) ? 'me' : 'ot'
    put(r.due_date, { run: r, sym: '제출 마감', what: STAGE_NAMES[r.stage], k, hour: 17 })
    if (r.stage === 'ENGINEER_REVIEW' || r.stage === 'REJECTED') put(before(r.due_date, 2), { run: r, sym: '상신 권장', what: `마감 ${dueText(r.due_date)}`, k, hour: 9 })
  }
  const place = (list: Ev[]) => {
    const order = [...list].sort((a, b) => a.hour - b.hour || a.run.review_no.localeCompare(b.run.review_no))
    const used = new Set<number>()
    const out: { e: Ev; at: number }[] = []
    let rest = 0
    for (const e of order) {
      let at = e.hour
      while (used.has(at) && at < H0 + NH - 1) at += 1
      if (used.has(at)) { rest += 1; continue }
      used.add(at)
      out.push({ e, at })
    }
    return { out, rest }
  }
  const shownN = days.reduce((n, d) => n + (evs[isoDay(d)]?.length ?? 0), 0)
  const mon = `${days[0].getFullYear()}년 ${days[0].getMonth() + 1}월`
  return (
    <div className="tc">
      <div className="tc-bar">
        <button type="button" className="bo" onClick={() => setOff(0)}>오늘</button>
        <button type="button" className="ib" onClick={() => setOff(off - 7)} aria-label="이전 7일"><span className="ms" aria-hidden="true">chevron_left</span></button>
        <button type="button" className="ib" onClick={() => setOff(off + 7)} aria-label="다음 7일"><span className="ms" aria-hidden="true">chevron_right</span></button>
        <span className="tc-mon" title={`${isoDay(days[0])} ~ ${isoDay(days[6])}`}>{mon}</span>
        <span style={{ flex: '1 1 0' }} />
        <span className="hm-mut">7일 보기 · 상신 권장 = 제출 마감 2일 전</span>
      </div>
      <div className="tc-g">
        <div className="tc-hd"><div className="tc-gut" />
          {days.map((d, i) => {
            const we = d.getDay() === 0 || d.getDay() === 6
            return <div key={i} className={`${we ? 'we' : ''}${off + i === 0 ? ' today' : ''}`}><span className="dn">{d.getDate()}</span><span className="dw">{WEEK[d.getDay()]}</span></div>
          })}</div>
        <div className="tc-bd">
          <div className="tc-gut">{Array.from({ length: NH }, (_, i) => <span key={i}>{String(H0 + i).padStart(2, '0')}:00</span>)}</div>
          {days.map((d, i) => {
            const day = isoDay(d)
            const we = d.getDay() === 0 || d.getDay() === 6
            const { out, rest } = place(evs[day] ?? [])
            return (
              <div key={day} className={`tc-c${we ? ' we' : ''}${off + i === 0 ? ' today' : ''}`} aria-label={`${d.getMonth() + 1}월 ${d.getDate()}일`}>
                {out.map(({ e, at }) => (
                  <a key={`${e.run.run_id}-${e.sym}`} className={`tc-e ${e.k}`} href={href(`/reviews/${e.run.run_id}`)} style={{ top: `calc(var(--hh) * ${at - H0} + 1px)` }}
                    title={`${e.run.review_no} · ${reviewTitle(e.run)} · ${TURN_NAMES[e.k]} · ${e.sym} ${dueText(day)}`}>
                    <span className="nm">{e.run.review_name ?? reviewTitle(e.run)}</span><span className="what">{e.sym} · {e.what}</span></a>
                ))}
                {rest > 0 && <span className="tc-e ot" style={{ top: `calc(var(--hh) * ${NH - 1} + 1px)` }}>+{rest}</span>}
              </div>
            )
          })}
        </div>
      </div>
      {!shownN && <p className="bd-emp">조건에 맞는 검토가 없습니다.</p>}
    </div>
  )
}

/** 어제 이후 바뀐 것 (update-home-projects design.md 4): 어제 0시 뒤 분석이 끝나거나 멈춘 내 검토,
 * 문서를 더해 다시 판정한 검토(add-revision-notice: 끝났으면 "분석 끝남" 대신 "문서 추가") */
function Changes({ runs, now }: { runs: RunListItem[]; now: number }) {
  const [open, setOpen] = useState(false)
  const t = new Date(now)
  const since = new Date(t.getFullYear(), t.getMonth(), t.getDate() - 1).getTime()
  const after = (iso: string | null | undefined) => !!iso && new Date(iso).getTime() >= since
  type Row = { r: RunListItem; kind: 'fail' | 'done' | 'add'; at: string }
  const rows: Row[] = runs.flatMap((r): Row[] => {
    if (r.stage === 'PROCESSING') return []
    if (r.stage === 'FAILED') return after(r.finished_at) ? [{ r, kind: 'fail', at: r.finished_at! }] : []
    if (r.revision && after(r.revision.at)) return [{ r, kind: 'add', at: r.revision.at }]
    return after(r.finished_at) ? [{ r, kind: 'done', at: r.finished_at! }] : []
  }).sort((a, b) => b.at.localeCompare(a.at))
  const n = (k: Row['kind']) => rows.filter((x) => x.kind === k).length
  const parts = [n('fail') && `분석 실패 ${n('fail')}`, n('add') && `문서 추가 ${n('add')}`, n('done') && `분석 끝남 ${n('done')}`].filter(Boolean)
  if (!rows.length) {
    return <section className="chg2" aria-label="어제 이후 바뀐 것"><div className="chg2-h"><b>어제 이후 바뀐 것 없음</b></div></section>
  }
  const ICON = { fail: 'error', done: 'task_alt', add: 'published_with_changes' }
  const TITLE = { fail: '분석이 멈췄습니다', done: '분석이 끝났습니다', add: '문서를 더해 다시 분석했습니다' }
  return (
    <section className="chg2" aria-label="어제 이후 바뀐 것">
      <button type="button" className="chg2-h" onClick={() => setOpen(!open)} aria-expanded={open}>
        <b>어제 이후 바뀐 것</b><span className="n">{rows.length}건</span><span className="sum">{parts.join(' · ')}</span>
        <span className="ms" aria-hidden="true">{open ? 'expand_less' : 'expand_more'}</span></button>
      {open && (
        <ul className="chg2-l">
          {rows.map(({ r, kind, at }) => (
            <li key={r.run_id} className={kind === 'fail' ? 'red' : kind === 'add' ? 'warn' : 'ok'}>
              <span className="ms" aria-hidden="true">{ICON[kind]}</span>
              <span className="tx"><b>{r.review_no} {reviewTitle(r)} · {TITLE[kind]}</b>
                <span>{kind === 'fail' ? `${STEP_NAMES[r.failed_step ?? ''] ?? '처리'} 단계`
                  : kind === 'add' ? `${r.revision!.files.join(', ')} · ${revisionText(r.revision!)}`
                    : `요구사항 ${r.requirements}건 · 일탈 후보 ${r.deviation_candidates}`} · {stamp(at)}</span></span>
              <span className="ac"><a className="bo sm" href={href(`/reviews/${r.run_id}${kind === 'add' ? '?rev=1' : ''}`)} aria-label={`${r.review_no} 가기`}>{kind === 'fail' ? '오류 내용 보기' : kind === 'add' ? '바뀐 줄 보기' : '가기'}</a></span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

const HTABS = [['team', '팀 업무'], ['notice', '공지사항'], ['sys', '시스템 공지'], ['file', '자료실']] as const
type HTab = typeof HTABS[number][0]

/** 팀원마다 지금 하는 일: 엔지니어는 마감이 가장 가까운 진행 중 검토, 승인자는 결재 대기, 담당자는 미확인 협조 요청 */
function teamRows(runs: RunListItem[], users: User[], asg: Assignment[][]) {
  const open = runs.filter((r) => r.stage !== 'APPROVED')
  const waiting = runs.filter((r) => r.stage === 'APPROVAL')
  const depts: Record<string, Assignment[]> = { COST: asg[0] ?? [], QUALITY: asg[1] ?? [], SALES: asg[2] ?? [] }
  return users.map((u) => {
    const base = { id: u.user_id, ini: u.user_name.slice(0, 1), name: u.user_name, role: ROLE_NAMES[u.role] ?? u.role }
    if (u.role === 'ENGINEER') {
      const mine = open.filter((r) => r.engineer_id === u.user_id).sort((a, b) => (left(a) ?? 999) - (left(b) ?? 999))
      const r = mine[0]
      if (!r) return { ...base, job: '맡은 검토 없음', ref: '', stage: '', tone: '', due: '', late: false, upd: '', to: '/reviews' }
      const n = left(r)
      return { ...base, job: reviewTitle(r), ref: [r.review_no, r.customer_name].filter(Boolean).join(' · ') + (mine.length > 1 ? ` 외 ${mine.length - 1}건` : ''),
        stage: STAGE_NAMES[r.stage], tone: `st ${STAGE_TONES[r.stage]}`, due: r.due_date ? `${dueText(r.due_date)} · ${dday(r.due_date).text}` : '',
        late: n !== null && n <= 4, upd: stamp(r.started_at), to: `/reviews/${r.run_id}` }
    }
    if (u.role === 'APPROVER') {
      return { ...base, job: waiting.length ? `결재 ${waiting.length}건 확인` : '결재 대기 없음', ref: waiting.map((r) => r.review_no).join(' · '),
        stage: waiting.length ? '결재 처리 중' : '', tone: 'st c-blue', due: '', late: false, upd: '', to: '/reviews' }
    }
    const todo = (depts[u.role] ?? []).filter((a) => a.status !== 'DONE')
    return { ...base, job: todo.length ? `협조 요청 ${todo.length}건 미확인` : '미확인 협조 요청 없음', ref: ROLE_NAMES[u.role] ?? '',
      stage: todo.length ? '협조 처리 중' : '', tone: 'st c-ora', due: '', late: false, upd: '', to: '/todo' }
  })
}

function TeamShare({ runs, users, pending }: { runs: RunListItem[]; users: User[]; pending: Assignment[][] }) {
  const [tab, setTab] = useState<HTab>('team')
  const [open, setOpen] = useState<Record<string, boolean>>({})
  const [got, setGot] = useState<Record<number, boolean>>({})
  const rows = teamRows(runs, users, pending)
  const toggle = (k: string) => setOpen({ ...open, [k]: !open[k] })
  const all = { team: ['/team', '팀 현황 전체 보기'], notice: ['/notice', '공지사항 전체 보기'], sys: ['/sysnotice', '시스템 공지 전체 보기'], file: ['/files', '자료실 전체 보기'] }[tab]
  return (
    <section className="sec" aria-labelledby="teamTitle">
      <div className="sech"><h2 id="teamTitle">엔지니어링팀 공유</h2><span className="hm-team">사용자 {users.length}명</span></div>
      <div className="pgtabs hm-tabs" role="tablist" aria-label="팀 공유">
        {HTABS.map(([k, label]) => (
          <button key={k} type="button" role="tab" className={tab === k ? 'on' : ''} aria-selected={tab === k} onClick={() => setTab(k)}>{label}
            {((k === 'notice' && NOTICES.some((n) => n.isNew)) || (k === 'sys' && SYS_NOTICES.some((n) => n.isNew))) && <i className="hm-new" title="새 글" />}</button>
        ))}
        <a className="hm-all" href={href(all[0])}>{all[1]}<span className="ms" aria-hidden="true">chevron_right</span></a>
      </div>
      {tab === 'team' && (
        <div className="hm-box">
          <div className="hm-th hm-tr"><span>담당자</span><span>지금 하는 일</span><span>단계</span><span>마감</span><span>최근 갱신</span><span /></div>
          {rows.map((m) => (
            <a key={m.id} className="hm-tr hm-row" href={href(m.to)}>
              <span className="hm-who"><span className="hm-av" aria-hidden="true">{m.ini}<i /></span><span className="hm-nm"><b>{m.name}</b><span>{m.role}</span></span></span>
              <span className="hm-job"><b className="ell">{m.job}</b><span className="mono ell">{m.ref}</span></span>
              <span>{m.stage && <span className={m.tone}>{m.stage}</span>}</span>
              <span className={`mono${m.late ? ' c-red' : ''}`}>{m.due}</span>
              <span className="mono hm-mut">{m.upd}</span>
              <span className="ms" aria-hidden="true" style={{ color: 'var(--c-disabled)' }}>chevron_right</span>
            </a>
          ))}
        </div>
      )}
      {tab === 'notice' && (
        <div className="hm-box">
          <ExampleBand />
          {NOTICES.map((n, i) => (
            <div key={n.title} className="hm-post">
              <button type="button" className="hm-ph" onClick={() => toggle(`n${i}`)} aria-expanded={!!open[`n${i}`]}>
                <span className="hm-pt">{n.must && <span className="st c-red">필독</span>}<b className="ell">{n.title}</b>{n.isNew && !open[`n${i}`] && <i className="hm-new" title="읽지 않음" />}</span>
                <span className="hm-mut">{n.by}</span><span className="mono hm-mut">{n.date}</span>
                <span className="ms" aria-hidden="true" style={{ color: 'var(--c-disabled)' }}>{open[`n${i}`] ? 'expand_less' : 'expand_more'}</span>
              </button>
              {open[`n${i}`] && <div className="hm-pb">{n.body}</div>}
            </div>
          ))}
        </div>
      )}
      {tab === 'sys' && (
        <div className="hm-box">
          <ExampleBand />
          {SYS_NOTICES.map((n, i) => (
            <div key={n.title} className="hm-post">
              <button type="button" className="hm-ph" onClick={() => toggle(`s${i}`)} aria-expanded={!!open[`s${i}`]}>
                <span className="hm-pt"><span className={n.tone}>{n.kind}</span><b className="ell">{n.title}</b>{n.isNew && !open[`s${i}`] && <i className="hm-new" title="읽지 않음" />}</span>
                <span className="hm-mut">{n.when}</span><span className="mono hm-mut">{n.date}</span>
                <span className="ms" aria-hidden="true" style={{ color: 'var(--c-disabled)' }}>{open[`s${i}`] ? 'expand_less' : 'expand_more'}</span>
              </button>
              {open[`s${i}`] && <div className="hm-pb">{n.body}</div>}
            </div>
          ))}
        </div>
      )}
      {tab === 'file' && (
        <div className="hm-box">
          <ExampleBand />
          {FILES.map((f, i) => (
            <div key={f.name} className="hm-file">
              <span className={`hm-ext${f.ext === 'XLSX' ? ' x' : ''}`}>{f.ext}</span>
              <span className="hm-fn"><b className="ell">{f.name}</b><span>{f.desc}</span></span>
              <span className="hm-mut">{f.by}</span><span className="mono hm-mut">{f.date} · {f.size}</span>
              <button type="button" className="bo" onClick={() => setGot({ ...got, [i]: true })} aria-label={`${f.name} 내려받기`}>
                <span className="ms" aria-hidden="true" style={{ fontSize: 'var(--ic-s)' }}>{got[i] ? 'check' : 'download'}</span>{got[i] ? '받음' : '내려받기'}</button>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

/** 교육·봉사·행사 예시: 세 장씩 넘겨 본다. 신청해도 저장하지 않는다 */
function Events() {
  const [at, setAt] = useState(0)
  const [done, setDone] = useState<Record<number, boolean>>({})
  const vis = 3
  const max = EVENTS.length - vis
  return (
    <section className="sec" aria-labelledby="evTitle">
      <div className="sech">
        <h2 id="evTitle">교육 · 봉사 · 행사</h2>
        <div className="hm-evc">
          <span className="mono hm-mut">{at + 1}–{at + vis} / {EVENTS.length}</span>
          <button type="button" className="hm-nav" onClick={() => setAt(Math.max(0, at - 1))} disabled={at === 0} aria-label="이전 행사"><span className="ms" aria-hidden="true">chevron_left</span></button>
          <button type="button" className="hm-nav" onClick={() => setAt(Math.min(max, at + 1))} disabled={at >= max} aria-label="다음 행사"><span className="ms" aria-hidden="true">chevron_right</span></button>
        </div>
      </div>
      <ExampleBand />
      <div className="hm-vp" aria-roledescription="carousel">
        <div className="hm-track" style={{ transform: `translateX(calc(${-at} * (100% + 16px) / ${vis}))` }}>
          {EVENTS.map((e, i) => {
            const closed = e.state === 'closed'
            const must = e.state === 'must'
            const tag = e.state.startsWith('open:') ? e.state.slice(5) : ''
            const on = !!done[i]
            return (
              <article key={e.title} className="hm-ev" aria-label={e.title}>
                <div className="hm-evh"><span className="hm-evi" aria-hidden="true"><span className="ms">{e.icon}</span></span><span className="hm-cat">{e.cat}</span>
                  <span className={closed ? 'st c-grey' : must ? 'st c-ora' : on ? 'st c-green' : 'st c-blue'}>{closed ? '마감' : must ? '필수' : on ? '신청함' : tag === '참석 표시' ? '자유 참석' : `신청 중 · ${tag}`}</span></div>
                <h3>{e.title}</h3>
                <dl>
                  <div><dt><span className="ms" aria-hidden="true">event</span><span className="sr">일시</span></dt><dd>{e.when}</dd></div>
                  <div><dt><span className="ms" aria-hidden="true">location_on</span><span className="sr">장소</span></dt><dd>{e.where}</dd></div>
                  <div><dt><span className="ms" aria-hidden="true">group</span><span className="sr">인원</span></dt><dd>{e.cap}</dd></div>
                </dl>
                <div className="hm-evf"><span className="hm-mut">{e.host}</span>
                  <button type="button" className={closed || on ? 'bo' : 'bp'} disabled={closed} onClick={() => setDone({ ...done, [i]: !on })}>
                    {closed ? '마감됨' : must ? (on ? '수강 확인됨' : '수강 확인') : on ? '신청 취소' : tag === '참석 표시' ? '참석 표시' : '신청하기'}</button></div>
              </article>
            )
          })}
        </div>
      </div>
      <div className="hm-dots" role="group" aria-label="행사 위치">
        {Array.from({ length: max + 1 }, (_, k) => <button key={k} type="button" className={k === at ? 'on' : ''} onClick={() => setAt(k)} aria-label={`${k + 1}번째 묶음`} aria-current={k === at} />)}
      </div>
    </section>
  )
}
