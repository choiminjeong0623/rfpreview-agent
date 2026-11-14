import { readFileSync } from 'node:fs'
import { expect, test, type APIRequestContext } from '@playwright/test'
import { as, deviationRun, dueIn, ENGINEER, openTab } from './helpers'

// 명세 review-workspace "지난 RFP 비교 탭"의 Scenario (change add-past-compare).
// 같은 고객사로 합성 데이터시트(지난 입찰)와 다음 입찰 데이터시트(e2e/fixtures/next_datasheet.docx,
// tests/docx_factory.build_judgment_spec_next: 값 바뀜·새로 생김·사라짐 한 줄씩)를 올려 비교한다.

async function upload(request: APIRequestContext, file: string, customer: string) {
  const res = await request.post('/api/runs', {
    multipart: {
      files: { name: file, mimeType: 'application/octet-stream', buffer: readFileSync(new URL(`./fixtures/${file}`, import.meta.url)) },
      review_name: `지난 비교 ${file}`, customer_name: customer, actor_id: String(ENGINEER), due_date: dueIn(),
      choices: JSON.stringify({ [file]: { bundle: 'A' } }),
    },
  })
  expect(res.status(), await res.text()).toBe(202)
  const run = await res.json() as { run_id: number; review_no: string }
  await expect.poll(async () => (await (await request.get(`/api/runs/${run.run_id}`)).json()).stage,
    { timeout: 60_000 }).toBe('ENGINEER_REVIEW')
  return run
}

test('같은 고객사 지난 검토와 비교', async ({ page, request }) => {
  const customer = `비교 고객 ${Date.now()}`
  const past = await upload(request, 'synthetic_judgment.docx', customer)
  const now = await upload(request, 'next_datasheet.docx', customer)
  await as(page, ENGINEER)
  await page.goto(`/#/reviews/${now.run_id}`)
  await openTab(page, '지난 RFP 비교')
  const cmp = page.locator('#cmp')
  await expect(cmp.getByLabel('비교 대상')).toHaveValue(String(past.run_id))
  await expect(cmp.getByRole('note')).toHaveCount(0)                     // 예시 띠 없음
  await expect(cmp.locator('.cmph')).toContainText(past.review_no)
  const rows = cmp.locator('table.tbl tbody tr')
  await expect(rows).toHaveCount(3)
  await expect(rows.first()).toContainText('4000 A')
  await expect(rows.first()).toContainText('3150 A')
  await cmp.getByRole('button', { name: /새로 생김/ }).click()
  await expect(cmp.getByRole('button', { name: /새로 생김/ })).toHaveAttribute('aria-pressed', 'true')
  await expect(rows).toHaveCount(1)
  await expect(rows).toContainText('125 kA')
  await expect(cmp.locator('.cmfoot')).toHaveText(/같은 요구 \d+건은 값과 판정이 지난번과 같아 숨겼습니다\./)
})

test('고객사 없음 안내', async ({ page, request }) => {
  const run = await deviationRun(request, `지난 비교 고객 없음 ${Date.now()}`)
  await as(page, ENGINEER)
  await page.goto(`/#/reviews/${run.run_id}`)
  await openTab(page, '지난 RFP 비교')
  const cmp = page.locator('#cmp')
  await expect(cmp.locator('.cmempty')).toContainText('고객사를 넣으면')
  await expect(cmp.locator('table')).toHaveCount(0)
})
