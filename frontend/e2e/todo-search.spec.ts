import { expect, test, type Page } from '@playwright/test'

// 명세 review-workspace "협조 요청 찾기"·"협조 요청 RFP별 보기"·"협조 요청 내보내기 단추"·"협조 요청 현황 화면"(재요청)의 Scenario
// (change update-todo-search). 협조 요청 목록 API를 테스트가 정한 값으로 바꿔 화면만 본다. 내보내기·재요청 API는 백엔드 tests/test_todo_search.py.

const H = 3_600_000
type A = Record<string, unknown> & { assignment_id: number; run_id: number; status: string; mail_sent_at: string | null }

function req(id: number, run: number, role: string, text: string, extra: Partial<A> = {}): A {
  const runs: Record<number, [string, string, string]> = {
    9301: ['RV-TEST-301', '115 kV GIS 1차', 'Thai Binh'], 9302: ['RV-TEST-302', '230 kV GIS 2차', 'Thai Binh'], 9303: ['RV-TEST-303', '변압기', 'Song Hau'],
  }
  const [no, name, pj] = runs[run]
  return {
    assignment_id: id, run_id: run, assignee_role: role, status: 'TODO', repeat_count: 1, sent_at: new Date().toISOString(), updated_at: null,
    requirement_id: id + 1000, requirement_ids: [id + 1000], point_id: null, point_kind: null, point_requirement_id: null, type_code: 'COST', type_name: '비용 영향',
    assignee: null, text, is_assumed: false, stage: 'ENGINEER_REVIEW', review_no: no, project_name: pj, review_name: name, customer_name: null, country: null,
    due_date: null, engineer_id: 1, engineer_name: '시험 엔지니어', business_id: null, business_no: null,
    locations: [{ file_no: 1, section_no: 'GCC 14', section_title: 'Delay', table_name: null, item_no: null, line_start: 120 + id, line_end: 120 + id }],
    file_name: 'synthetic_gcc.docx', mail_sent_at: null, mail_to: null, mail_error: null, sent_by_name: null,
    dept_address: role === 'COST' ? 'cost@example.com' : role === 'QUALITY' ? 'quality@example.com' : 'sales@example.com',
    replied_at: null, replied_by_name: null, reply_note: null, ask_text: null, ask_by: null, ...extra,
  }
}

const ago = (h: number) => new Date(Date.now() - h * H).toISOString()
const sentAgo = (h: number, role = 'cost'): Partial<A> => ({ status: 'DOING', mail_sent_at: ago(h), mail_to: `${role}@example.com` })

async function mock(page: Page, userId = 1, more: A[] = []) {
  const list: A[] = [
    req(1, 9301, 'COST', 'Liquidated damages for delay 0.5 % per week', sentAgo(120)),
    req(2, 9301, 'COST', 'Performance security 10 % of contract price', sentAgo(100)),
    req(3, 9301, 'COST', 'Spare parts for five years of operation', sentAgo(30)),
    req(4, 9302, 'COST', 'Transport to site including insurance', { ...sentAgo(80), status: 'DONE', replied_at: ago(10), reply_note: '운반 포함' }),
    req(5, 9302, 'COST', 'Witness test travel cost by supplier', { is_assumed: true }),
    req(6, 9303, 'COST', 'Warranty period 36 months after taking over'),
    req(7, 9303, 'COST', 'Delay damages cap 10 %'),
    req(8, 9303, 'COST', 'Price adjustment not allowed'),
    req(9, 9301, 'QUALITY', 'Type Test Report shall be submitted', { type_code: 'TEST', type_name: '시험' }),
    req(10, 9303, 'SALES', 'Bid validity 180 days', { type_code: 'CONTRACT', type_name: '계약 조건' }),
    ...more,
  ]
  const posts: { path: string; body: Record<string, unknown> }[] = []
  await page.route('**/api/**', async (r) => {
    const url = new URL(r.request().url())
    const path = url.pathname
    if (path === '/api/users') {
      return r.fulfill({ json: [{ user_id: 1, user_name: '시험 엔지니어', role: 'ENGINEER' }, { user_id: 3, user_name: '시험 품질', role: 'QUALITY' }] })
    }
    if (path === '/api/assignments') return r.fulfill({ json: list })
    if (path === '/api/assignments/export') {
      posts.push({ path, body: r.request().postDataJSON() })
      return r.fulfill({ body: 'xlsx', contentType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers: { 'Content-Disposition': `attachment; filename*=UTF-8''${encodeURIComponent('협조요청_견적 담당.xlsx')}`, 'X-Row-Count': '5' } })
    }
    const send = path.match(/^\/api\/runs\/\d+\/assignments\/send$/)
    if (send) {
      const body = r.request().postDataJSON() as { assignment_ids: number[]; resend: boolean }
      posts.push({ path, body })
      for (const a of list) if (body.assignment_ids.includes(a.assignment_id)) Object.assign(a, { status: 'DOING', mail_sent_at: new Date().toISOString() })
      return r.fulfill({ json: { sent: 1, failed: 0, no_address: 0, mails: 1 } })
    }
    return r.fulfill({ json: [] })
  })
  await page.addInitScript((id) => localStorage.setItem('s2w.user', String(id)), userId)
  return posts
}

const rows = (page: Page) => page.locator('.tw tbody tr')
const count = (page: Page) => page.locator('.sech h2 span')
const bar = (page: Page) => page.getByRole('search', { name: '협조 요청 찾기' })

test('탭 이름 옆 부서별 건수', async ({ page }) => {
  await mock(page)
  await page.goto('/#/todo')
  const tabs = page.getByRole('navigation', { name: '수신 부서' })
  await expect(tabs.getByRole('button', { name: /견적 담당/ }).locator('.c')).toHaveText('8')
  await expect(tabs.getByRole('button', { name: /품질 담당/ }).locator('.c')).toHaveText('1')
  await expect(tabs.getByRole('button', { name: /미분류/ }).locator('.c')).toHaveText('0')
})

test('검색 영역으로 거르기', async ({ page }) => {
  await mock(page)
  await page.goto('/#/todo')
  await expect(count(page)).toHaveText('8')
  await bar(page).getByLabel('사업').selectOption('Thai Binh')
  await bar(page).getByRole('button', { name: '검색' }).click()
  await expect(count(page)).toHaveText('5')
  await expect(rows(page)).toHaveCount(5)
  const chips = page.locator('.fchips')
  await expect(chips).toContainText('5건')
  await chips.getByRole('button', { name: /사업: Thai Binh/ }).click()
  await expect(count(page)).toHaveText('8')
  await expect(page.locator('.fchips')).toHaveCount(0)
})

test('회신 기한 지남', async ({ page }) => {
  await mock(page)
  await page.goto('/#/todo')
  await bar(page).getByLabel('회신').selectOption('over')
  await bar(page).getByRole('button', { name: '검색' }).click()
  await expect(rows(page)).toHaveCount(2)
  await expect(rows(page).locator('.rpl.od')).toHaveCount(2)
  await expect(rows(page).first().locator('.rpl.od')).toContainText(/회신 기한 \d\d-\d\d 지남/)
  // 요약 줄 상태를 누르면 그 상태만
  await page.getByRole('button', { name: '초기화' }).click()
  await page.locator('.sumline').getByRole('button', { name: /회신 완료/ }).click()
  await expect(rows(page)).toHaveCount(1)
  await expect(rows(page).locator('.rpl.ok')).toContainText('회신')
})

test('조건에 맞는 요청 없음', async ({ page }) => {
  await mock(page)
  await page.goto('/#/todo')
  await bar(page).getByLabel('검색어').fill('없는 낱말')
  await bar(page).getByRole('button', { name: '검색' }).click()
  await expect(page.getByText('조건에 맞는 요청이 없습니다.')).toBeVisible()
  await expect(page.locator('.emp').getByRole('button')).toHaveCount(0)        // 문장만, 조건 지우기 단추 없음 (update-todo-empty-text)
  await page.getByRole('button', { name: '초기화' }).click()                    // 조건은 검색 영역 초기화·칩으로 푼다
  await expect(count(page)).toHaveText('8')
})

test('RFP별 묶어 보기', async ({ page }) => {
  await mock(page)
  await page.goto('/#/todo')
  await page.getByRole('group', { name: '보기 방식' }).getByRole('button', { name: 'RFP별' }).click()
  const groups = page.locator('.rg')
  await expect(groups).toHaveCount(3)
  const g = page.getByRole('region', { name: 'RV-TEST-302 협조 요청' })
  await expect(g.locator('.rg-s')).toContainText('회신 1 / 2')
  const g1 = page.getByRole('region', { name: 'RV-TEST-301 협조 요청' })
  await expect(g1.locator('.rg-dp')).toContainText('견적 3')
  await expect(g1.locator('.rg-dp')).toContainText('품질 1')
  await expect(g1.locator('.rg-od')).toHaveText('기한 지남 2')
  await expect(g.locator('tbody tr')).toHaveCount(2)
  await g.getByRole('button', { name: 'RV-TEST-302 접기' }).click()
  await expect(g.locator('table')).toHaveCount(0)
  await g.getByRole('button', { name: 'RV-TEST-302 펼치기' }).click()
  await expect(g.locator('tbody tr')).toHaveCount(2)
})

// 명세 review-workspace "협조 요청 RFP별 보기" (change update-todo-rfp-paging)
test('RFP별 쪽 나누기', async ({ page }) => {
  // 302 검토에 요청 5건을 더해 모두 15건: 301 4건 → 302 7건 → 303 4건 순서로 10건씩 자른다
  await mock(page, 1, [11, 12, 13, 14, 15].map((id) => req(id, 9302, 'QUALITY', `Routine test item ${id}`, { type_code: 'TEST', type_name: '시험' })))
  await page.goto('/#/todo')
  await page.getByRole('group', { name: '보기 방식' }).getByRole('button', { name: 'RFP별' }).click()
  await expect(page.locator('.rg tbody tr')).toHaveCount(10)
  await expect(page.locator('.pager')).toContainText('1–10 / 전체 15건')
  const g = page.getByRole('region', { name: 'RV-TEST-302 협조 요청' })
  await expect(g.locator('tbody tr')).toHaveCount(6)
  await expect(g.locator('.rg-s')).toContainText('회신 1 / 7')          // 머리 숫자는 검토 전체
  await expect(page.getByRole('region', { name: 'RV-TEST-303 협조 요청' })).toHaveCount(0)
  await page.getByRole('button', { name: '다음 페이지' }).click()
  await expect(page.locator('.rg tbody tr')).toHaveCount(5)
  await expect(g.locator('tbody tr')).toHaveCount(1)                     // 302의 남은 1건이 이어진다
  await expect(page.getByRole('region', { name: 'RV-TEST-303 협조 요청' }).locator('tbody tr')).toHaveCount(4)
  await expect(page.getByRole('region', { name: 'RV-TEST-301 협조 요청' })).toHaveCount(0)
})

test('협조 요청 내보내기', async ({ page }) => {
  const posts = await mock(page)
  await page.goto('/#/todo')
  await bar(page).getByLabel('사업').selectOption('Thai Binh')
  await bar(page).getByRole('button', { name: '검색' }).click()
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: '내보내기' }).click()
  await download
  await expect(page.getByRole('status')).toContainText('협조요청_견적 담당.xlsx를 만들었습니다.')
  const body = posts.find((p) => p.path === '/api/assignments/export')!.body
  expect(body).toEqual({ role: 'COST', assignment_ids: [1, 2, 3, 4, 5] })
})

test('재요청', async ({ page }) => {
  const posts = await mock(page)
  await page.goto('/#/todo')
  const r = rows(page).filter({ hasText: 'Spare parts' })
  await expect(r.locator('.st').first()).toHaveText('24시간 넘게 회신 없음')
  await r.getByRole('button', { name: '재요청' }).click()
  await expect(page.getByRole('status')).toContainText('다시 보냈습니다')
  const due = new Date(Date.now() + 72 * H)
  const md = `${String(due.getMonth() + 1).padStart(2, '0')}-${String(due.getDate()).padStart(2, '0')}`
  await expect(r.locator('.rpl')).toHaveText(`회신 기한 ${md}`)
  await expect(r.locator('.st').first()).toHaveText('회신 대기')
  expect(posts.find((p) => p.path.endsWith('/assignments/send'))!.body).toMatchObject({ assignment_ids: [3], resend: true })
})

test('재요청은 엔지니어만', async ({ page }) => {
  await mock(page, 3)
  await page.goto('/#/todo')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('품질 담당')
  await page.getByRole('navigation', { name: '수신 부서' }).getByRole('button', { name: /견적 담당/ }).click()
  await expect(rows(page)).toHaveCount(5)
  await expect(page.getByRole('button', { name: '재요청' })).toHaveCount(0)
})
