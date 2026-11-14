import { expect, test, type Page } from '@playwright/test'

// 명세 review-workspace "홈 화면"(오늘 할 일 순서·오늘 할 일 없음·일정 달력·어제 이후 바뀐 것·홈에서 다시 시도),
// "사업 현황 화면"(요약 칸 설명 줄·요약 칸으로 거르기), "사업 상세 화면"(사업 상세에서 인계 패키지·승인 전 잠김)의 Scenario
// (change update-home-projects). API를 테스트가 정한 값으로 바꿔 화면만 본다. 단계별·사업별·팀 공유는 e2e/home.spec.ts(실제 백엔드).

const DAY = 86_400_000
const p2 = (n: number) => String(n).padStart(2, '0')
/** 오늘부터 n일 뒤 YYYY-MM-DD */
function after(n: number): string {
  const t = new Date()
  const d = new Date(t.getFullYear(), t.getMonth(), t.getDate() + n)
  return `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())}`
}
const md = (iso: string) => iso.slice(5)

type R = Record<string, unknown> & { run_id: number }
function run(id: number, name: string, extra: Partial<R> = {}): R {
  return {
    project_name: '예시 변전소', review_name: name, customer_name: null, country: null, due_date: null, engineer_id: 1,
    business_id: null, business_no: null, run_id: id, review_no: `RV-TEST-${id}`, engineer_name: '시험 엔지니어',
    stage: 'ENGINEER_REVIEW', step: null, step_detail: null, step_updated_at: new Date(Date.now() - 3 * DAY).toISOString(),
    failed_step: null, error_message: null, started_at: new Date(Date.now() - 3 * DAY).toISOString(),
    finished_at: new Date(Date.now() - 3 * DAY).toISOString(), files: 'spec.docx', requirements: 40, risks: 2,
    deviation_candidates: 1, proposals: 0, approver_id: null, approver: null, requested_by_id: null, requested_by: null,
    requested_at: null, decision: null, decided_at: null, ...extra,
  }
}

async function mock(page: Page, runs: R[], opts: { userId?: number; businesses?: unknown; business?: unknown } = {}) {
  const posts: string[] = []
  await page.route('**/api/**', async (r) => {
    const url = new URL(r.request().url())
    const path = url.pathname
    if (path === '/api/users') {
      return r.fulfill({ json: [{ user_id: 1, user_name: '시험 엔지니어', role: 'ENGINEER' }, { user_id: 2, user_name: '시험 승인자', role: 'APPROVER' }] })
    }
    if (path === '/api/runs') return r.fulfill({ json: runs })
    const jc = path.match(/^\/api\/runs\/(\d+)\/judgment-counts$/)
    if (jc) {
      return r.fulfill({ json: { by_result: { NEEDS_REVIEW: Number(jc[1]) % 100, COMPLY: 3 }, total: 20, unconfirmed: 10, unconfirmed_comply: 3, past_seen: 0, past_differs: 0 } })
    }
    const retry = path.match(/^\/api\/runs\/(\d+)\/retry$/)
    if (retry) {
      posts.push(path)
      const target = runs.find((x) => x.run_id === Number(retry[1]))!
      Object.assign(target, { stage: 'PROCESSING', step: 'classify' })
      return r.fulfill({ status: 202, json: target })
    }
    if (path === '/api/businesses') return r.fulfill({ json: opts.businesses ?? { summary: { open: 0, due3: 0, overdue: 0 }, items: [] } })
    if (/^\/api\/businesses\/\d+$/.test(path)) return r.fulfill({ json: opts.business })
    if (/^\/api\/runs\/\d+\/handoffs$/.test(path)) return r.fulfill({ json: [] })
    return r.fulfill({ json: [] })
  })
  await page.addInitScript((id) => localStorage.setItem('s2w.user', String(id)), opts.userId ?? 1)
  return posts
}

const today = (page: Page) => page.locator('section.td')

test('오늘 할 일 순서', async ({ page }) => {
  await mock(page, [
    run(9406, '230 kV GIS', { due_date: after(6) }),
    run(9403, '115 kV GIS', { due_date: after(3) }),
    run(9409, '변압기', { stage: 'APPROVAL', engineer_id: 1, approver_id: 2, due_date: after(9) }),   // 승인자 차례
  ])
  await page.goto('/#/')
  const items = today(page).locator('.td-l li')
  await expect(items).toHaveCount(2)
  await expect(items.first()).toContainText('RV-TEST-9403')
  await expect(items.first()).toContainText(`상신 권장 ${md(after(1))} (D-1)`)
  await expect(items.first()).toContainText('확인 필요 3건')
  await expect(items.first().getByRole('link', { name: '판정 확인' })).toHaveAttribute('href', '#/reviews/9403')
  await expect(items.nth(1)).toContainText('RV-TEST-9406')
  // "내가 처리할 건" 수는 내 차례인 검토 수와 같다
  await expect(page.locator('.qsum button', { hasText: '내가 처리할 건' }).locator('b')).toHaveText('2')
  await expect(page.locator('.qsum button', { hasText: '결재 대기' }).locator('b')).toHaveText('1')
  await expect(page.locator('.qsum button', { hasText: '마감 경과' })).toHaveCount(0)
})

test('오늘 할 일 없음', async ({ page }) => {
  await mock(page, [run(9410, '승인된 검토', { stage: 'APPROVED', due_date: after(5) })])
  await page.goto('/#/')
  await expect(today(page)).toContainText('지금 내 차례인 검토가 없습니다.')
})

test('일정 달력', async ({ page }) => {
  await mock(page, [run(9404, '115 kV GIS 일정', { due_date: after(4) })])
  await page.goto('/#/')
  await expect(page.getByRole('button', { name: '일정', exact: true })).toHaveAttribute('aria-pressed', 'true')
  const dueDay = new Date(Date.now() + 4 * DAY)
  const subDay = new Date(Date.now() + 2 * DAY)
  const cell = (d: Date) => page.getByLabel(`${d.getMonth() + 1}월 ${d.getDate()}일`, { exact: true })
  await expect(cell(dueDay).locator('.tc-e')).toContainText('제출 마감')
  await expect(cell(dueDay).locator('.tc-e')).toContainText('115 kV GIS 일정')
  await expect(cell(subDay).locator('.tc-e')).toContainText('상신 권장')
  await expect(cell(subDay).locator('.tc-e')).toHaveAttribute('href', '#/reviews/9404')
  // 다음 7일로 가면 그 검토가 보이지 않는다
  await page.getByRole('button', { name: '다음 7일' }).click()
  await expect(page.getByText('조건에 맞는 검토가 없습니다.')).toBeVisible()
})

test('어제 이후 바뀐 것', async ({ page }) => {
  await mock(page, [
    run(9411, '어제 끝난 검토', { finished_at: new Date().toISOString() }),
    run(9412, '오래된 검토'),
  ])
  await page.goto('/#/')
  const chg = page.getByRole('region', { name: '어제 이후 바뀐 것' })
  const head = chg.getByRole('button', { name: /어제 이후 바뀐 것/ })
  await expect(head).toContainText('1건')
  await expect(head).toContainText('분석 끝남 1')
  await head.click()
  await expect(chg.locator('li')).toHaveCount(1)
  await expect(chg.locator('li')).toContainText('RV-TEST-9411')
  await expect(chg.getByRole('link', { name: 'RV-TEST-9411 가기' })).toHaveAttribute('href', '#/reviews/9411')
})

test('어제 이후 바뀐 것 없음', async ({ page }) => {
  await mock(page, [run(9412, '오래된 검토')])
  await page.goto('/#/')
  await expect(page.getByRole('region', { name: '어제 이후 바뀐 것' })).toContainText('어제 이후 바뀐 것 없음')
})

test('홈에서 다시 시도', async ({ page }) => {
  const posts = await mock(page, [run(9413, '배전반', { stage: 'FAILED', failed_step: 'risks', error_message: '언어 모델이 응답하지 않았습니다.', due_date: after(4) })])
  await page.goto('/#/')
  const alert = page.getByRole('alert').filter({ hasText: '분석이 멈췄습니다' })
  await expect(alert.getByRole('button', { name: '재시도' })).toBeEnabled()
  // 오늘 할 일에도 실패 이유와 재시도가 보인다
  await expect(today(page).locator('.td-l li').first()).toContainText('위험 조건 찾기에서 멈춤 · 마감 D-4')
  await alert.getByRole('button', { name: '재시도' }).click()
  await expect(page.getByText('다시 분석을 시작했습니다')).toBeVisible()
  expect(posts).toEqual(['/api/runs/9413/retry'])
})

test('승인자는 다시 시도할 수 없다', async ({ page }) => {
  await mock(page, [run(9414, '배전반', { stage: 'FAILED', failed_step: 'risks' })], { userId: 2 })
  await page.goto('/#/')
  const alert = page.getByRole('alert').filter({ hasText: '분석이 멈췄습니다' })
  await expect(alert.getByRole('button', { name: '재시도' })).toBeDisabled()
  await expect(alert.getByRole('button', { name: '재시도' })).toHaveAttribute('title', '엔지니어만 다시 시도할 수 있습니다')
})

// 사업 현황·사업 상세

function biz(id: number, name: string, days: number | null, ranges: Partial<Record<string, unknown>>[] = [], extra: Record<string, unknown> = {}) {
  return {
    business_id: id, business_no: `PJ-2026-${String(id).padStart(3, '0')}`, business_name: name, customer_name: '시험 고객', country: '베트남',
    tender_no: null, order_mode: null, business_due_date: days === null ? null : after(days), due_date: days === null ? null : after(days), days_left: days,
    sales_id: null, sales_name: null, created_by: 1, created_by_name: '시험 엔지니어', created_at: new Date().toISOString(), submitted_at: null, my_role: 'ENGINEER',
    ranges: ranges.map((r, i) => ({ run_id: 9500 + id * 10 + i, review_no: `RV-TEST-${9500 + id * 10 + i}`, review_name: `범위 ${i + 1}`, stage: 'ENGINEER_REVIEW',
      due_date: null, started_at: new Date().toISOString(), engineer_id: 1, engineer_name: '시험 엔지니어', open_requests: 0, state: 'chk', ...r })),
    ...extra,
  }
}

const LIST = {
  summary: { open: 4, due3: 2, overdue: 1 },
  items: [
    biz(1, '하노이 변전소', 2, [{}, { engineer_id: 7 }]),
    biz(2, '호찌민 변전소', 3, [{}]),
    biz(3, '다낭 변전소', 20, [{}]),
    biz(4, '후에 변전소', -2, [{}]),
  ],
}

test('요약 칸 설명 줄', async ({ page }) => {
  await mock(page, [], { businesses: LIST })
  await page.goto('/#/projects')
  const due3 = page.locator('.sh-sum.qk button', { hasText: '3일 내 제출 마감' })
  await expect(due3.locator('b')).toHaveText('2')
  await expect(due3.locator('.qs')).toHaveText('하노이 변전소 D-2 · 호찌민 변전소 D-3')
  await expect(page.locator('.sh-sum.qk button', { hasText: '진행 중 사업' }).locator('.qs')).toHaveText('설비 범위 5개 · 내 담당 4개')
  await expect(page.locator('.sh-sum.qk button', { hasText: '마감 지남' }).locator('.qs')).toHaveText('후에 변전소')
})

test('요약 칸으로 거르기', async ({ page }) => {
  await mock(page, [], { businesses: LIST })
  await page.goto('/#/projects')
  await expect(page.locator('.pl-row')).toHaveCount(4)
  await page.locator('.sh-sum.qk button', { hasText: '3일 내 제출 마감' }).click()
  await expect(page.locator('.pl-row')).toHaveCount(2)
  await expect(page.locator('.qkbar')).toContainText('3일 내 제출 마감 2건만 보는 중')
  await page.locator('.qkbar').getByRole('button', { name: '모두 보기' }).click()
  await expect(page.locator('.pl-row')).toHaveCount(4)
  await expect(page.locator('.qkbar')).toHaveCount(0)
})

const detail = (stage: string) => ({ ...biz(5, '광양 변전소', 10, [{ stage, state: stage === 'APPROVED' ? 'sub' : 'ap', review_name: '154 kV GIS' }]), people: [], schedule: [], documents: [] })

test('사업 상세에서 인계 패키지', async ({ page }) => {
  await mock(page, [], { business: detail('APPROVED') })
  await page.goto('/#/projects/PJ-2026-005')
  await page.getByRole('button', { name: '인계 패키지 보기' }).click()
  const dlg = page.getByRole('dialog', { name: '인계 패키지' })
  await expect(dlg).toContainText('RV-TEST-9550')
  await expect(dlg).toContainText('154 kV GIS')
  await expect(dlg.getByRole('button', { name: '인계 패키지 내려받기' })).toBeVisible()
  await expect(dlg.getByRole('button', { name: '영업에 넘기기' })).toBeVisible()
})

test('승인 전 잠김', async ({ page }) => {
  await mock(page, [], { business: detail('APPROVAL') })
  await page.goto('/#/projects/PJ-2026-005')
  const btn = page.getByRole('button', { name: '인계 패키지 보기' })
  await expect(btn).toBeDisabled()
  await expect(btn).toHaveAccessibleDescription('결재가 승인된 검토가 없습니다')
})

// 명세 review-workspace "검토 목록 내가 처리할 건"의 Scenario (change update-list-my-turn)
test('목록 내가 처리할 건은 홈과 같은 수', async ({ page }) => {
  await mock(page, [
    run(9501, '담당자 확인'),
    run(9502, '반려됨', { stage: 'REJECTED' }),
    run(9503, '남의 검토', { engineer_id: 7 }),
    run(9504, '승인 끝', { stage: 'APPROVED' }),
  ])
  await page.goto('/#/')
  await expect(page.locator('.qsum button', { hasText: '내가 처리할 건' }).locator('b')).toHaveText('2')
  await page.goto('/#/reviews')
  const cell = page.locator('.sumline button', { hasText: '내가 처리할 건' })
  await expect(cell.locator('b')).toHaveText('2')
  await expect(cell).toHaveAttribute('title', /반려됨/)
  await page.getByRole('group', { name: '담당 범위' }).getByRole('button', { name: '팀 전체' }).click()
  await expect(cell.locator('b')).toHaveText('2')
})

// 명세 review-workspace "인계 패키지 미리 보기" — 사업 상세에서 미리 보기 (change add-package-preview)
test('사업 상세에서 미리 보기', async ({ page }) => {
  await mock(page, [], { business: detail('APPROVED') })
  // 미리 보기 창이 부르는 것만 이 검토 값으로 돌려준다 (나중에 건 route가 먼저)
  await page.route(/\/api\/runs\/9550(\/(tbe|cost-conditions|approval))?(\?.*)?$/, (r) => {
    const p = new URL(r.request().url()).pathname
    if (p.endsWith('/tbe')) return r.fulfill({ json: { file_name: '', review_no: 'RV-TEST-9550', project_name: null, review_name: null, rows: [],
      counts: { rows: 0, comply: 0, deviation: 0, query: 0, review: 0, candidates: 0, no_location: 0 } } })
    if (p.endsWith('/cost-conditions')) return r.fulfill({ json: { conditions: [], impacts: [] } })
    if (p.endsWith('/approval')) return r.fulfill({ json: { stage: 'APPROVED', approval: null, reasons: [], preview: null, review_ratio: null, submission_check: null, read_unchecked: 0 } })
    return r.fulfill({ json: run(9550, '115 kV GIS', { stage: 'APPROVED' }) })
  })
  await page.goto('/#/projects/PJ-2026-005')
  await page.getByRole('button', { name: '인계 패키지 보기' }).click()
  await page.getByRole('dialog', { name: '인계 패키지' }).getByRole('button', { name: '미리 보기' }).click()
  const dlg = page.getByRole('dialog', { name: '영업 인계 패키지' })
  await expect(dlg).toContainText('RV-TEST-9550')
  await expect(dlg.getByRole('tab', { name: /영업 할 일/ })).toBeVisible()
  await page.unrouteAll({ behavior: 'ignoreErrors' })
})

// 명세 review-workspace "검토 목록 요약 줄 결재 완료·분석 중" (change update-list-summary-rest)
test('요약 줄 결재 완료·분석 중', async ({ page }) => {
  await mock(page, [
    run(9601, '확인 1'), run(9602, '확인 2'),
    run(9603, '결재 중', { stage: 'APPROVAL', approver_id: 2 }),
    run(9604, '완료 1', { stage: 'APPROVED' }), run(9605, '완료 2', { stage: 'APPROVED' }),
    run(9606, '분석', { stage: 'PROCESSING', step: 'documents' }),
  ])
  await page.goto('/#/reviews')
  const line = page.locator('.sumline')
  const num = (label: string) => line.locator('span, button', { hasText: label }).locator('b')
  await expect(num('내가 처리할 건')).toHaveText('2')
  await expect(num('결재 대기')).toHaveText('1')
  await expect(num('결재 완료')).toHaveText('2')
  await expect(num('분석 중')).toHaveText('1')
  await expect(page.locator('.sech h2')).toContainText('6')
  await expect(line.locator('.sumrest', { hasText: '결재 완료' })).toHaveAttribute('title', /결재가 승인/)
})

// 명세 review-workspace "요약 줄 칸으로 거르기" (change update-list-summary-filter)
const SUM_LIST = () => [
  run(9701, '확인 1'), run(9702, '확인 2'), run(9703, '결재 중', { stage: 'APPROVAL', approver_id: 2 }),
  run(9704, '완료 1', { stage: 'APPROVED' }), run(9705, '완료 2', { stage: 'APPROVED' }),
]

test('검토 목록 요약 칸으로 거르기', async ({ page }) => {
  await mock(page, SUM_LIST())
  await page.goto('/#/reviews')
  const rows = page.locator('table.tbl tbody tr')
  await expect(rows).toHaveCount(5)
  const done = page.locator('.sumline').getByRole('button', { name: /결재 완료/ })
  await done.click()
  await expect(page).toHaveURL(/#\/reviews\?sum=approved$/)
  await expect(rows).toHaveCount(2)
  await expect(page.locator('.sumbar')).toContainText('결재 완료 2건만 보는 중')
  await expect(done).toHaveAttribute('aria-pressed', 'true')
  for (const [label, n] of [['내가 처리할 건', 2], ['결재 대기', 1]] as const) {     // 다른 칸도 거른다
    await page.locator('.sumline').getByRole('button', { name: new RegExp(label) }).click()
    await expect(rows).toHaveCount(n)
  }
  await page.locator('.sumline').getByRole('button', { name: /결재 대기/ }).click()   // 다시 누르면 풂
  await expect(rows).toHaveCount(5)
  await expect(page.locator('.sumbar')).toHaveCount(0)
})

test('뒤로 가기로 전체 목록', async ({ page }) => {
  await mock(page, SUM_LIST())
  await page.goto('/#/reviews')
  const rows = page.locator('table.tbl tbody tr')
  await expect(rows).toHaveCount(5)
  await page.locator('.sumline').getByRole('button', { name: /내가 처리할 건/ }).click()
  await expect(rows).toHaveCount(2)
  await page.goBack()
  await expect(page).toHaveURL(/#\/reviews$/)
  await expect(rows).toHaveCount(5)
  await expect(page.locator('.sumbar')).toHaveCount(0)
})
