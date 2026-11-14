import { expect, test } from '@playwright/test'
import { ENGINEER, as, deviationRun } from './helpers'

// 명세 review-workspace "상업 조건 탭"의 Scenario (change add-cost-conditions, FR-16, update-comm-tab-layout).
// 합성 데이터시트에는 상업 조항이 없어, 비용 조건 줄은 응답을 바꿔 넣는다(상업 영향의 일탈 줄은 실제 데이터).

const LOC = { file_no: 91, section_no: '3', section_title: 'COMMERCIAL CONDITIONS', table_name: null, item_no: null, line_start: 40, line_end: 40 }
const row = (id: number, kind: string, text: string, extra: Record<string, unknown> = {}) => ({
  requirement_id: id, requirement_ids: [id], kind, text, values: [], burden: null, risk: null, primary_type: 'COST',
  primary_type_name: '비용 영향', repeat_count: 1, role: 'COST', assignment_id: id, request_status: 'TODO', mail_error: null,
  file_name: 'synthetic_judgment.docx', locations: [LOC], ...extra,
})
const CONDITIONS = [
  row(900001, '지체상금', 'Liquidated damages shall be 0.5 % of the Contract Price per week of delay.', { values: ['0.5 %'] }),
  row(900002, '책임 한도', "The Contractor's total liability shall not be limited.", { risk: '책임 한도 없음', request_status: 'DOING' }),
  row(900003, '하자 보증', 'The Defects Notification Period shall be 24 months from Taking-Over.', { values: ['24 months'] }),
  row(900004, '하자 보증', 'The warranty period for spare parts shall be 12 months after delivery.', { values: ['12 months'] }),
  row(900005, '시험 입회', 'Type Test shall be witnessed by the Employer.', { primary_type: 'TEST', primary_type_name: '시험', assignment_id: null, request_status: null }),
]

test('상업 조건 탭 열기', async ({ page, request }) => {
  const run = await deviationRun(request, `상업 조건 ${Date.now()}`)
  await page.route(`**/api/runs/${run.run_id}/cost-conditions`, async (route) => {
    const res = await route.fetch()
    const body = await res.json()
    await route.fulfill({ response: res, json: { ...body, conditions: CONDITIONS } })
  })
  await as(page, ENGINEER)
  await page.goto(`/#/reviews/${run.run_id}`)
  await page.getByRole('tab', { name: '상업 조건' }).click()
  const comm = page.locator('#comm')
  await expect(comm.getByRole('note')).toHaveCount(0)                           // 예시 띠 없음
  await expect(comm.locator('.sech .note')).toContainText('비용 조건 5')
  const ld = comm.locator('tr', { hasText: 'Liquidated damages' })
  await expect(ld).toContainText('지체상금')
  await expect(ld.locator('.cmv')).toHaveText('0.5 %')                          // 값 먼저
  await expect(ld.locator('td.loc')).toContainText('3 COMMERCIAL CONDITIONS · 40행')   // 줄인 위치
  await expect(ld.locator('td.loc')).toHaveAttribute('title', /synthetic_judgment\.docx/)
  await expect(comm.locator('.cmh').first()).toContainText('견적 담당 확인')
  await expect(ld).not.toContainText('견적 담당')
  await expect(ld.locator('.st').last()).toHaveText('미발송')
  await expect(comm.locator('tr', { hasText: 'total liability' })).toContainText('책임 한도 없음')
  await expect(comm.locator('tr', { hasText: 'witnessed' }).locator('.st').last()).toHaveText('협조 요청 없음')
  await expect(comm.locator('tr', { hasText: '일탈 가격 영향' }).first()).toBeVisible()      // 실제 일탈 후보
})

test('종류 칩으로 거르기', async ({ page, request }) => {
  const run = await deviationRun(request, `상업 조건 칩 ${Date.now()}`)
  await page.route(`**/api/runs/${run.run_id}/cost-conditions`, async (route) => {
    const res = await route.fetch()
    await route.fulfill({ response: res, json: { ...(await res.json()), conditions: CONDITIONS } })
  })
  await page.goto(`/#/reviews/${run.run_id}`)
  await page.getByRole('tab', { name: '상업 조건' }).click()
  const comm = page.locator('#comm')
  const chip = comm.getByRole('group', { name: '조항 종류' }).getByRole('button', { name: /하자 보증/ })
  await expect(chip).toContainText('2')
  await chip.click()
  await expect(chip).toHaveAttribute('aria-pressed', 'true')
  await expect(comm.locator('table.cmt').first().locator('tr')).toHaveCount(2)
  await expect(comm.locator('table.cmt').first()).not.toContainText('Liquidated damages')
})

test('비용 조건이 없는 검토', async ({ page, request }) => {
  const run = await deviationRun(request, `상업 조건 없음 ${Date.now()}`)
  await page.goto(`/#/reviews/${run.run_id}`)
  await page.getByRole('tab', { name: '상업 조건' }).click()
  const comm = page.locator('#comm')
  await expect(comm.getByText('찾은 비용 조건이 없습니다')).toBeVisible()
  await expect(comm.getByRole('button', { name: /내려받기|보내기|전달/ })).toHaveCount(0)
})

test('상업 조건 원문 펼치기', async ({ page, request }) => {
  const run = await deviationRun(request, `상업 조건 펼치기 ${Date.now()}`)
  await page.route(`**/api/runs/${run.run_id}/cost-conditions`, async (route) => {
    const res = await route.fetch()
    await route.fulfill({ response: res, json: { ...(await res.json()), conditions: CONDITIONS } })
  })
  await page.goto(`/#/reviews/${run.run_id}`)
  await page.getByRole('tab', { name: '상업 조건' }).click()
  const comm = page.locator('#comm')
  const toggle = comm.locator('table.cmt').getByRole('button', { name: '지체상금', exact: true })
  await expect(toggle).toHaveAttribute('aria-expanded', 'false')
  await toggle.click()
  await expect(toggle).toHaveAttribute('aria-expanded', 'true')
  const full = comm.locator('tr.cmopen')
  await expect(full.locator('.cmfull')).toContainText('per week of delay')
  await expect(full.locator('mark')).toHaveText('0.5 %')
  await expect(full.locator('.cmlocs')).toContainText('synthetic_judgment.docx')
  await comm.locator('tr.cmrow', { hasText: '지체상금' }).click()           // 줄을 다시 누르면 접힘
  await expect(comm.locator('tr.cmopen')).toHaveCount(0)
  await page.unrouteAll({ behavior: 'ignoreErrors' })
})

test('같은 상업 영향 묶기', async ({ page, request }) => {
  const run = await deviationRun(request, `상업 영향 묶기 ${Date.now()}`)
  const loss = (n: number) => ({ kind: 'LOSS', loss_calc_id: 800000 + n, item_id: null, judgment_id: null, product_code: null,
    total_usd: null, is_assumed: false, text: null, locations: [{ ...LOC, line_start: 7000 + n, line_end: 7000 + n }] })
  await page.route(`**/api/runs/${run.run_id}/cost-conditions`, async (route) => {
    const res = await route.fetch()
    const body = await res.json()
    await route.fulfill({ response: res, json: { ...body, impacts: [loss(1), loss(2), loss(3), ...body.impacts] } })
  })
  await page.goto(`/#/reviews/${run.run_id}`)
  await page.getByRole('tab', { name: '상업 조건' }).click()
  const rows = page.locator('#comm tr', { hasText: '손실 환산 가산액' })
  await expect(rows).toHaveCount(1)
  await expect(rows).toContainText('같은 조건 3곳')
  await expect(rows.locator('td.loc')).toContainText('외 2곳')
  await expect(rows.getByRole('button', { name: '손실 환산 →' })).toBeVisible()
  await page.unrouteAll({ behavior: 'ignoreErrors' })
})

// change update-comm-impact-open
test('상업 영향 펼치기', async ({ page, request }) => {
  const run = await deviationRun(request, `상업 영향 펼치기 ${Date.now()}`)
  await page.goto(`/#/reviews/${run.run_id}`)
  await page.getByRole('tab', { name: '상업 조건' }).click()
  const comm = page.locator('#comm')
  const row = comm.locator('tr.cmrow', { hasText: '일탈 가격 영향' }).first()
  await row.click()
  await expect(row.getByRole('button', { name: '일탈 가격 영향' })).toHaveAttribute('aria-expanded', 'true')
  const open = comm.locator('tr.cmopen')
  await expect(open.locator('.cmfull')).toContainText('요구값')
  await expect(open.locator('.cmlocs li').first()).toBeVisible()
  await row.click()                                                                // 다시 누르면 접힘
  await expect(comm.locator('tr.cmopen')).toHaveCount(0)
  await row.getByRole('button', { name: '판정 →' }).click()                        // 이동 단추는 펼치지 않고 판정 탭으로
  await expect(page.getByRole('tab', { name: /판정/ }).first()).toHaveAttribute('aria-selected', 'true')
})

test('종류 모르는 문서 위치', async ({ page, request }) => {
  const run = await deviationRun(request, `종류 모름 ${Date.now()}`)
  await page.route(`**/api/runs/${run.run_id}/documents`, async (route) => {
    const res = await route.fetch()
    const docs = (await res.json()) as { doc_kind: string }[]
    await route.fulfill({ response: res, json: docs.map((d) => ({ ...d, doc_kind: 'UNKNOWN' })) })
  })
  await page.goto(`/#/reviews/${run.run_id}`)
  await page.getByRole('tab', { name: '상업 조건' }).click()
  const loc = page.locator('#comm tr.cmrow', { hasText: '일탈 가격 영향' }).first().locator('td.loc')
  await expect(loc).toContainText('synthetic_judgment.docx')
  await expect(loc).not.toContainText('종류 모름')
  await page.unrouteAll({ behavior: 'ignoreErrors' })
})
