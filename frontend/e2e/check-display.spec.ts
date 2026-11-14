import { readFileSync } from 'node:fs'
import { expect, test, type APIRequestContext } from '@playwright/test'
import { ENGINEER, as, dueIn } from './helpers'

// 명세 review-workspace "판정 탭의 공학 검산 표시"의 Scenario (change update-check-display, FR-12).
// 합성 데이터시트 e2e/fixtures/synthetic_check.docx (백엔드 tests/test_engineering_check.build_check_spec, 고객 원문 아님):
// TS-230-CB 50 Hz 차단 50 kA·최대 순간 100 kA → 위반, TS-145-DS 주파수 없음 → 확인 필요, TS-115-GIS 40·100 kA → 통과.

async function checkRun(request: APIRequestContext) {
  const file = 'synthetic_check.docx'
  const res = await request.post('/api/runs', {
    multipart: {
      files: { name: file, mimeType: 'application/octet-stream', buffer: readFileSync(new URL(`./fixtures/${file}`, import.meta.url)) },
      review_name: `검산 표시 ${Date.now()}`, actor_id: String(ENGINEER), due_date: dueIn(), choices: JSON.stringify({ [file]: { bundle: 'A' } }),
    },
  })
  expect(res.status(), await res.text()).toBe(202)
  const run = await res.json() as { run_id: number }
  await expect.poll(async () => (await (await request.get(`/api/runs/${run.run_id}`)).json()).stage,
    { timeout: 60_000 }).toBe('ENGINEER_REVIEW')
  return run.run_id
}

/** 표에서 그 표(table_name)의 최대 순간 전류 줄 */
const peakRow = (page: import('@playwright/test').Page, table: string) =>
  page.locator('#judge table.tbl tbody tr', { hasText: 'Rated peak withstand current' }).filter({ hasText: table })

test.beforeEach(async ({ page }) => { await as(page, ENGINEER) })

test('검산 위반 줄', async ({ page, request }) => {
  const id = await checkRun(request)
  await page.goto(`/#/reviews/${id}`)
  await page.getByRole('combobox', { name: '한 페이지에 보일 개수' }).selectOption('50')
  await expect(page.locator('#judge .chkn')).toContainText('공학 검산 위반 1건(표시한 항목 2개) · 확인 필요 1건(표시한 항목 2개)')
  const bad = page.locator('#judge table.tbl tbody tr', { has: page.locator('.tag.chk.bad') })
  await expect(bad).toHaveCount(2)                          // 검산 하나 = 차단 전류 줄 + 최대 순간 전류 줄 (update-check-banner-rows)
  await expect(bad.filter({ hasText: 'Rated short-circuit breaking current' })).toHaveCount(1)
  await expect(bad.filter({ hasText: 'Rated peak withstand current' })).toHaveCount(1)
  await expect(peakRow(page, 'TS-145-DS').locator('.tag.chk.warn')).toHaveText('검산 확인 필요')
})

test('검산 계산식 보기', async ({ page, request }) => {
  const id = await checkRun(request)
  await page.goto(`/#/reviews/${id}`)
  await page.getByRole('combobox', { name: '한 페이지에 보일 개수' }).selectOption('50')
  const row = page.locator('#judge table.tbl tbody tr', { has: page.locator('.tag.chk.bad'), hasText: 'peak' }).first()
  await row.locator('td').nth(2).click()
  const panel = page.locator('.jv')                         // 판정 상세 화면 (update-judge-tab-preview)
  await expect(panel).toContainText('공학 검산')
  await expect(panel).toContainText('50 kA × 2.5 = 125 kA')
  await expect(panel).toContainText('원문 최대 순간 전류 100')
  await expect(panel).toContainText('위반')
})

test('통과한 검산', async ({ page, request }) => {
  const id = await checkRun(request)
  await page.goto(`/#/reviews/${id}`)
  await page.getByRole('combobox', { name: '한 페이지에 보일 개수' }).selectOption('50')
  const row = peakRow(page, 'TS-115-GIS')
  await expect(row.locator('.tag.chk')).toHaveCount(0)
  await row.locator('td').nth(2).click()
  const panel = page.locator('.jv')                         // 판정 상세 화면 (update-judge-tab-preview)
  await expect(panel).toContainText('통과')
  await expect(panel).toContainText('40 kA × 2.5 = 100 kA')
})

// 명세 review-workspace "판정 상세 검산 확인"의 Scenario (change add-check-calculator). 계산은 서버 규칙(GET /engineering/peak-check)
test('판정 상세에서 검산 확인', async ({ page, request }) => {
  const id = await checkRun(request)
  await page.goto(`/#/reviews/${id}`)
  await page.getByRole('combobox', { name: '한 페이지에 보일 개수' }).selectOption('50')
  await peakRow(page, 'TS-230-CB').locator('td').nth(2).click()
  const box = page.getByRole('region', { name: '검산 확인' })
  await expect(box).toContainText('판정은 바뀌지 않습니다')
  const peak = box.getByLabel('최대 순간 전류', { exact: true })
  await expect(peak).toHaveValue('100')
  await expect(box.getByRole('status')).toContainText('위반')
  await peak.fill('125')
  await expect(box.getByRole('status')).toContainText('통과')
  await expect(box).toContainText('50 kA × 2.5 = 125 kA')
  await box.getByRole('button', { name: '원문 값으로' }).click()
  await expect(peak).toHaveValue('100')
  await expect(box.getByRole('status')).toContainText('위반')
})
