import { useCallback, useState } from 'react'
import { api, type RunListItem } from '../api'
import { dday, dueText, filesText, isoDay, num, scopeName, stamp } from '../components/format'
import { STAGE_NAMES, STAGE_TONES, STEP_NAMES } from '../components/labels'
import { myTurn } from '../components/myWork'
import { Pager } from '../components/Pager'
import { useLoad, useRepeat } from '../components/useLoad'
import { progress, STALL_MS, stepLine } from '../components/progress'
import { currentPath, href, navigate, pathQuery, useHashPath } from '../shell/router'
import { useSession } from '../shell/useSession'
import './detail.css'

// SCR-06 검토 목록 (목업 v4.57 Main). docs/screens/SCR-06-검토목록.md

type Period = '1w' | '1m' | 'all'
type Has = '' | 'requirements' | 'risks' | 'deviation_candidates' | 'proposals'
type Field = 'all' | 'name' | 'id' | 'file'
type SortKey = 'started' | 'requirements' | 'dev'
type Search = { stage: string; has: Has; field: Field; q: string }
type Scope = 'mine' | 'all' | 'submitted' | number
// "내가 올린 결재" 보기의 결정 칩 (update-review-list-approval)
type Ap = 'all' | 'wait' | 'rej' | 'ok'
const APS: [Ap, string][] = [['all', '전체'], ['wait', '결재 대기'], ['rej', '반려'], ['ok', '승인']]

const PERIODS: [Period, string][] = [['1w', '1주'], ['1m', '1개월'], ['all', '전체']]
const HAS: [Has, string][] = [['', '전체'], ['requirements', '요구사항'], ['risks', '위험'], ['deviation_candidates', '일탈'],
  ['proposals', '제안']]
const STAGES = ['PROCESSING', 'ENGINEER_REVIEW', 'APPROVAL', 'APPROVED', 'REJECTED', 'FAILED']
const PLACEHOLDER: Record<Field, string> = {
  all: '사업명, 검토명, 번호, 고객사, 파일명', name: '사업명·검토명 (예: Thai Binh)', id: '번호 (예: RV-2026-025)', file: '파일명',
}
const EMPTY: Search = { stage: 'all', has: '', field: 'all', q: '' }

function daysAgo(n: number): Date {
  const d = new Date()
  d.setDate(d.getDate() - n)
  return d
}

const FROM: Record<Period, Date | null> = { '1w': daysAgo(6), '1m': daysAgo(30), all: null }

function rangeText(period: Period): string {
  const from = FROM[period]
  return from ? `${isoDay(from).slice(5)}–${isoDay(new Date()).slice(5)}` : '전체 기간'
}

function matches(r: RunListItem, field: Field, q: string): boolean {
  if (!q) return true
  const name = [r.project_name, r.review_name].join(' ')
  const text = { all: [name, r.review_no, r.files, r.customer_name].join(' '), name, id: r.review_no, file: r.files ?? '' }[field]
  return text.toLowerCase().includes(q.toLowerCase())
}

function apState(r: RunListItem): Ap | null {
  if (!r.requested_at) return null
  return r.decision === 'REJECTED' ? 'rej' : r.decision === 'APPROVED' ? 'ok' : 'wait'
}

/** 첫 화면 담당 범위: `#/reviews?scope=submitted`면 내가 올린 결재 */
function initialScope(): Scope {
  const q = currentPath().split('?')[1] ?? ''
  return new URLSearchParams(q).get('scope') === 'submitted' ? 'submitted' : 'mine'
}

function ApprovalCell({ r, now }: { r: RunListItem; now: number }) {
  const st = apState(r)
  if (!st) return <span className="dimv">—</span>
  const days = Math.max(0, Math.floor((now - new Date(r.requested_at!).getTime()) / 86_400_000))
  return (
    <div style={{ whiteSpace: 'nowrap' }}>
      <span style={{ fontWeight: 600 }}>{r.approver ?? '결재자 없음'}</span>
      <div className="cond" style={{ marginTop: 1 }}>
        {st === 'wait' ? `상신 ${days}일째` : `${st === 'rej' ? '반려' : '승인'} ${stamp(r.decided_at!)}`}
      </div>
    </div>
  )
}

function Count({ v, hot, processing }: { v: number; hot?: string; processing: boolean }) {
  if (processing) return <span className="dimv">—</span>
  return <span className={v === 0 ? 'dimv' : hot ?? ''}>{num(v)}</span>
}

function Row({ r, seq, me, now, clock }: { r: RunListItem; seq: number; me: number | null; now: number | null; clock: number }) {
  const scope = scopeName(r)
  const detail = href(`/reviews/${r.run_id}`)
  const processing = r.stage === 'PROCESSING'
  const failed = r.stage === 'FAILED'
  const step = STEP_NAMES[(failed ? r.failed_step : r.step) ?? ''] ?? (failed ? r.failed_step : r.step)
  const due = r.due_date ? dday(r.due_date) : null
  return (
    <tr className={r.stage === 'APPROVED' || r.stage === 'REJECTED' ? 'dis' : ''}>
      <td className="num mono" style={{ color: 'var(--c-muted)' }}>{seq}</td>
      <td><span className={`st ${STAGE_TONES[r.stage]}`}>{STAGE_NAMES[r.stage]}</span>{processing && <RowProgress r={r} clock={clock} />}</td>
      <td>{r.project_name && <span className="pjn">{r.project_name}</span>}</td>
      <td>
        {failed || r.stage === 'APPROVAL'
          ? <a className="failnm" href={detail}>{scope}</a>
          : <a href={detail} style={{ color: 'var(--c-text)', fontWeight: 600 }}>{scope}</a>}
        {failed && step && <a className="tag failtag" href={detail}>{step}에서 멈춤<span className="ms" aria-hidden="true">chevron_right</span></a>}
        {processing && step && <span className="tag">{step} 중</span>}
        <div className="cond meta">
          <span>{r.review_no}</span>
          {r.customer_name && <span>{r.customer_name}</span>}
          {r.files && <span className="ell" style={{ maxWidth: 150 }} title={r.files}>{filesText(r.files)}</span>}
          {r.engineer_name && <span>{r.engineer_name}</span>}
          {r.engineer_id !== null && r.engineer_id !== me && (
            <span className="rotag"><span className="ms" aria-hidden="true">visibility</span>열람</span>
          )}
        </div>
      </td>
      <td style={{ whiteSpace: 'nowrap' }}>
        {r.stage === 'APPROVED' ? <span className="dd dimv">완료</span>
          : r.stage === 'REJECTED' ? <span className="dd">—</span>
            : due && <span className={`dd ${due.cls}`}>{due.text}</span>}
        {r.due_date && <div className="cond" style={{ marginTop: 1 }}>{dueText(r.due_date)}</div>}
      </td>
      <td style={{ whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums' }}>{stamp(r.started_at)}</td>
      <td className="num"><Count v={r.requirements} processing={processing} /></td>
      <td className="num"><Count v={r.risks} processing={processing || failed} /></td>
      <td className="num"><Count v={r.deviation_candidates} hot="neg" processing={processing || failed} /></td>
      <td className="num"><Count v={r.proposals} processing={processing || failed} /></td>
      {now !== null && <td><ApprovalCell r={r} now={now} /></td>}
      <td><a className="dots" href={detail} aria-label={`${r.review_no} 열기`}><span className="ms" aria-hidden="true">more_horiz</span></a></td>
    </tr>
  )
}

/** 처리 중인 줄의 진행 막대와 단계 (목업 v4.96 목록 줄 진행 막대). 10분 넘게 진행이 없으면 주황 */
function RowProgress({ r, clock }: { r: RunListItem; clock: number }) {
  const p = progress(r)
  const stalled = clock - Date.parse(r.step_updated_at) > STALL_MS
  return (
    <div className={'lprog' + (stalled ? ' warn' : '')}>
      <div className="anbar" role="progressbar" aria-label={`${r.review_no} 진행`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={p}>
        <i style={{ width: `${p}%` }} />
      </div>
      <div className="lprog-t">{stepLine(r)}</div>
    </div>
  )
}

function SortHead({ k, label, sort, onSort, num: isNum }: {
  k: SortKey; label: string; sort: { key: SortKey; dir: 'asc' | 'desc' }; onSort: (k: SortKey) => void; num?: boolean
}) {
  const on = sort.key === k
  return (
    <th className={isNum ? 'num' : undefined} aria-sort={on ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'}>
      <button type="button" className={'sort' + (on ? ' on' : '')} onClick={() => onSort(k)}>
        {label}<span className="ms" aria-hidden="true">{on ? (sort.dir === 'asc' ? 'arrow_upward' : 'arrow_downward') : 'unfold_more'}</span>
      </button>
    </th>
  )
}

// 요약 줄 칸 거르기 (update-list-summary-filter): 주소 `?sum=`에 남겨 뒤로 가기로 풀린다
type Sum = 'mine' | 'approval' | 'failed' | 'approved' | 'processing'
const SUM_STAGE: Record<Exclude<Sum, 'mine'>, string> = { approval: 'APPROVAL', failed: 'FAILED', approved: 'APPROVED', processing: 'PROCESSING' }
const SUM_NAMES: Record<Sum, string> = { mine: '내가 처리할 건', approval: '결재 대기', failed: '분석 실패', approved: '결재 완료', processing: '분석 중' }
const toSum = (v: string | null): Sum | null => (v && v in SUM_NAMES ? (v as Sum) : null)

const MY_TURN_TIP = '담당자 확인·반려됨·분석 실패인 내 검토와 내가 결재할 결재 대기'

export function ReviewList() {
  const { user, users } = useSession()
  const runs = useLoad(() => api.runs(), [])
  const [clock, setClock] = useState(() => Date.now())   // 목록 줄 진행의 멈춤 판단 기준 (다시 볼 때마다 새로)
  const { reload } = runs
  const refresh = useCallback(() => { reload(); setClock(Date.now()) }, [reload])
  useRepeat(!!runs.data?.some((r) => r.stage === 'PROCESSING'), refresh)   // 처리 중이면 5초마다 다시 본다
  const [period, setPeriod] = useState<Period>('all')
  const [scope, setScope] = useState<Scope>(initialScope)
  const [ap, setAp] = useState<Ap>('all')
  const [now] = useState(() => Date.now())          // 상신 후 날 수 기준 (화면을 연 때)
  const [draft, setDraft] = useState<Search>(EMPTY)
  const [search, setSearch] = useState<Search>(EMPTY)
  const [sort, setSort] = useState<{ key: SortKey; dir: 'asc' | 'desc' }>({ key: 'started', dir: 'desc' })
  const [page, setPage] = useState(1)
  const [size, setSize] = useState(10)
  const me = user?.user_id ?? null
  const all = runs.data ?? []
  const sum = toSum(pathQuery(useHashPath()).get('sum'))
  const submitted = scope === 'submitted'
  // 내가 올린 결재: 머리글에서 고른 사용자가 가장 최근에 상신한 검토 (취소한 상신은 빠짐)
  const owned = all.filter((r) => scope === 'all' || (submitted ? r.requested_by_id === me && me !== null
    : r.engineer_id === (scope === 'mine' ? me : scope)))
  const from = FROM[period]
  const key = { started: (r: RunListItem) => r.started_at, requirements: (r: RunListItem) => r.requirements,
    dev: (r: RunListItem) => r.deviation_candidates }[sort.key]
  const dir = sort.dir === 'asc' ? 1 : -1
  // 요약 칸으로 거르면 칸 숫자와 같은 목록에서 시작한다 (칸은 기간을 보지 않는다)
  const pool = sum === 'mine' ? all.filter(myTurn(user)) : sum ? owned.filter((r) => r.stage === SUM_STAGE[sum]) : owned
  const base = pool
    .filter((r) => !!sum || !from || r.started_at.slice(0, 10) >= isoDay(from))
    .filter((r) => search.stage === 'all' || r.stage === search.stage)
    .filter((r) => !search.has || r[search.has] > 0)
    .filter((r) => matches(r, search.field, search.q.trim()))
  // 결정 칩 개수는 다른 거름(기간·찾기)을 적용한 뒤의 수
  const apCount = (k: Ap) => base.filter((r) => k === 'all' || apState(r) === k).length
  const rows = base
    .filter((r) => !submitted || ap === 'all' || apState(r) === ap)
    .sort((a, b) => (key(a) > key(b) ? dir : key(a) < key(b) ? -dir : 0))
  const pages = Math.max(1, Math.ceil(rows.length / size))
  const cur = Math.min(page, pages)
  const shown = rows.slice((cur - 1) * size, cur * size)
  const count = (stage: string) => owned.filter((r) => r.stage === stage).length
  // 홈 "내가 처리할 건"과 같은 규칙·같은 목록 (update-list-my-turn). 담당 범위·기간 거름과 상관없다
  const myCount = all.filter(myTurn(user)).length
  const engineers = users.filter((u) => u.role === 'ENGINEER' && u.user_id !== me)
  const other = typeof scope === 'number' ? users.find((u) => u.user_id === scope) : null
  const apply = (s: Search) => { setSearch(s); setPage(1) }
  const pick = (k: Sum) => { setPage(1); navigate(sum === k ? '/reviews' : `/reviews?sum=${k}`) }
  /** 요약 칸 단추: 누르면 거르고, 다시 누르면 푼다 */
  const cell = (k: Sum, n: number, tone: string, extra = '', tip?: string) => (
    <button type="button" className={`sumlink ${extra}${sum === k ? ' on' : ''}`} aria-pressed={sum === k}
      title={(tip ? tip + ' · ' : '') + (sum === k ? '다시 누르면 모두 보기' : '누르면 이 검토만 보입니다')} onClick={() => pick(k)}>
      {SUM_NAMES[k]}<b className={tone}>{n}</b></button>
  )
  const onSort = (k: SortKey) => setSort({ key: k, dir: sort.key === k && sort.dir === 'desc' ? 'asc' : 'desc' })
  return (
    <main className="main">
      <div className="ttl">
        <h1>검토 목록</h1>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <div className="seg" role="group" aria-label="기간">
            {PERIODS.map(([k, l]) => (
              <button key={k} type="button" className={period === k ? 'on' : ''} aria-pressed={period === k}
                onClick={() => { setPeriod(k); setPage(1) }}>{l}</button>
            ))}
          </div>
          <span className="range">{rangeText(period)}</span>
          <a className="bp" href={href('/register')}><span className="ms" aria-hidden="true" style={{ fontSize: 'var(--ic-s)' }}>add</span>검토 등록</a>
        </div>
      </div>

      <div className="sumline">
        {cell('mine', myCount, 'c-blue', '', MY_TURN_TIP)}
        {cell('approval', count('APPROVAL'), '')}
        {cell('failed', count('FAILED'), 'c-red')}
        {/* 할 일이 아닌 단계: 칸 합이 목록 수와 맞게 (update-list-summary-rest) */}
        {cell('approved', count('APPROVED'), '', 'sumrest sumsep', '결재가 승인되어 더 할 일이 없는 검토')}
        {(count('PROCESSING') > 0 || sum === 'processing') && cell('processing', count('PROCESSING'), '', 'sumrest', '문서를 분석하고 있는 검토')}
      </div>
      {sum && (
        <div className="sumbar" role="status"><span className="ms" aria-hidden="true">filter_alt</span>
          <span><b>{SUM_NAMES[sum]} {rows.length}건</b>만 보는 중</span>
          <button type="button" className="lnk" onClick={() => { setPage(1); navigate('/reviews') }}>모두 보기</button></div>
      )}

      <section className="sec">
        <div className="sech">
          <h2>검토 <span style={{ fontWeight: 400, color: 'var(--c-muted)' }}>{rows.length}</span></h2>
          <div className="own">
            <div className="seg" role="group" aria-label="담당 범위">
              {([['mine', '내 검토'], ['all', '팀 전체'], ['submitted', '내가 올린 결재']] as const).map(([k, l]) => (
                <button key={k} type="button" className={scope === k ? 'on' : ''} aria-pressed={scope === k}
                  onClick={() => { setScope(k); setAp('all'); setPage(1) }}>{l}</button>
              ))}
            </div>
            <label className="ownl"><span>담당자</span>
              <select className="fi" aria-label="담당자 고르기" value={typeof scope === 'number' ? scope : ''}
                onChange={(e) => { setScope(e.target.value ? Number(e.target.value) : 'mine'); setPage(1) }}>
                <option value="">선택</option>
                {engineers.map((u) => (
                  <option key={u.user_id} value={u.user_id}>
                    {u.user_name} ({all.filter((r) => r.engineer_id === u.user_id).length})</option>
                ))}
              </select>
            </label>
          </div>
        </div>
        {other && (
          <div className="ronote"><span className="ms" aria-hidden="true">visibility</span>
            <span><b>{other.user_name}</b>의 검토를 보고 있습니다.</span></div>
        )}
        {submitted && (
          <div className="apchips" role="group" aria-label="결재 결정">
            {APS.map(([k, l]) => (
              <button key={k} type="button" className={'apchip' + (ap === k ? ' on' : '')} aria-pressed={ap === k}
                onClick={() => { setAp(k); setPage(1) }}>{l} <b>{apCount(k)}</b></button>
            ))}
          </div>
        )}
        <div className="sp" role="search" aria-label="검토 찾기">
          <div className="sp-r1">
            <label className="sp-f"><span className="sp-l">단계</span>
              <select className="fi" value={draft.stage} onChange={(e) => setDraft({ ...draft, stage: e.target.value })}>
                <option value="all">모든 단계</option>
                {STAGES.map((s) => <option key={s} value={s}>{STAGE_NAMES[s]}</option>)}
              </select>
            </label>
            <div className="sp-f" role="radiogroup" aria-label="있는 항목"><span className="sp-l">있는 항목</span>
              {HAS.map(([k, l]) => (
                <label key={k} className="sp-rd">
                  <input type="radio" name="has" checked={draft.has === k} onChange={() => setDraft({ ...draft, has: k })} />{l}
                </label>
              ))}
            </div>
          </div>
          <div className="sp-r2">
            <select className="fi sp-qf" aria-label="검색 대상" value={draft.field}
              onChange={(e) => setDraft({ ...draft, field: e.target.value as Field })}>
              <option value="all">-전체-</option><option value="name">검토명</option><option value="id">번호</option>
              <option value="file">파일명</option>
            </select>
            <input className="fi sp-q" aria-label="검색어" placeholder={PLACEHOLDER[draft.field]} value={draft.q}
              onChange={(e) => setDraft({ ...draft, q: e.target.value })}
              onKeyDown={(e) => { if (e.key === 'Enter') apply(draft) }} />
            <button type="button" className="bo" onClick={() => { setDraft(EMPTY); apply(EMPTY) }}>초기화</button>
            <button type="button" className="bp" onClick={() => apply(draft)}>
              <span className="ms" aria-hidden="true" style={{ fontSize: 'var(--ic-s)' }}>search</span>검색</button>
          </div>
        </div>
        {runs.error && (
          <p className="neg" role="alert" style={{ margin: '16px 0 0' }}>{runs.error}{' '}
            <button type="button" className="bo" onClick={runs.reload}>다시 불러오기</button></p>
        )}
        <div className="tw">
          <table className="tbl">
            <thead><tr>
              <th className="num" style={{ width: 44 }}>순번</th>
              <th style={{ width: 110 }}>단계</th>
              <th style={{ width: 120 }}>사업명</th>
              <th style={{ width: '30%' }}>설비 범위</th>
              <th>마감</th>
              <SortHead k="started" label="시작" sort={sort} onSort={onSort} />
              <SortHead k="requirements" label="요구사항" sort={sort} onSort={onSort} num />
              <th className="num">위험</th>
              <SortHead k="dev" label="일탈" sort={sort} onSort={onSort} num />
              <th className="num">제안</th>
              {submitted && <th style={{ width: 120 }}>결재</th>}
              <th style={{ width: 28 }} />
            </tr></thead>
            <tbody>
              {runs.data === null && !runs.error && (
                <tr><td colSpan={submitted ? 12 : 11} className="dimv">불러오는 중…</td></tr>
              )}
              {shown.map((r, i) => <Row key={r.run_id} r={r} seq={(cur - 1) * size + i + 1} me={me} now={submitted ? now : null} clock={clock} />)}
            </tbody>
          </table>
          <Pager total={rows.length} page={cur} size={size} shown={shown.length} onPage={setPage}
            onSize={(n) => { setSize(n); setPage(1) }} />
        </div>
        {runs.data !== null && rows.length === 0 && (
          <p style={{ margin: 0, padding: '16px 12px', color: 'var(--c-muted)' }}>
            {submitted && owned.length === 0 ? '내가 상신한 검토가 없습니다.' : '조건에 맞는 검토가 없습니다.'}</p>
        )}
      </section>
    </main>
  )
}
