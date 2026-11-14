import { expect, test } from '@playwright/test'
import { ENGINEER, as, deviationRun } from './helpers'

// 명세 review-workspace "판정 탭 한꺼번에 확정"의 Scenario (change add-bulk-confirm).

test('고른 줄 확정', async ({ page, request }) => {
  const run = await deviationRun(request, `고른 줄 확정 ${Date.now()}`)
  await as(page, ENGINEER)
  await page.goto(`/#/reviews/${run.run_id}`)
  const rows = page.locator('#judge tbody tr')
  const unconfirmed = rows.filter({ hasNot: page.locator('.cfm') })
  await expect(unconfirmed.first()).toBeVisible()
  const before = await rows.locator('.cfm').count()
  await unconfirmed.nth(0).getByRole('checkbox').check()
  await unconfirmed.nth(1).getByRole('checkbox').check()
  const bar = page.locator('#judge .bulk').filter({ hasText: '2건 선택' })
  await expect(bar).toBeVisible()
  await bar.getByRole('button', { name: '제안대로 확정' }).click()
  await expect(page.getByRole('status').filter({ hasText: '판정 2건을 일괄 확정했습니다.' })).toBeVisible()
  await expect(rows.locator('.cfm')).toHaveCount(before + 2)
  await expect(page.locator('#judge .bulk').filter({ hasText: '건 선택' })).toHaveCount(0)
})

test('준수 모두 확정', async ({ page, request }) => {
  const run = await deviationRun(request, `준수 모두 확정 ${Date.now()}`)
  await as(page, ENGINEER)
  await page.goto(`/#/reviews/${run.run_id}`)
  // 확정 안 한 준수 줄은 화면 아래 행동 줄의 "준수 n줄은 모두 확정"으로 확정한다 (update-detail-header)
  const quick = page.locator('.ftb').getByRole('button', { name: '모두 확정' })
  await expect(quick).toBeVisible()
  await quick.click()
  await expect(page.locator('.uisnk').filter({ hasText: /판정 \d+건을 일괄 확정했습니다/ })).toBeVisible()
  await expect(quick).toHaveCount(0)
  const left = await (await request.get(`/api/runs/${run.run_id}/judgments?result=COMPLY&unconfirmed=true&limit=1`)).json()
  expect(left).toEqual([])
})

// 명세 review-workspace "한꺼번에 확정에서 뺀 줄 알림" (change update-bulk-confirm-guard).
// 합성 문서에는 검산 위반 줄이 없어, 응답에 뺀 줄을 넣어 화면 알림만 본다.
test('뺀 줄 알림', async ({ page, request }) => {
  const run = await deviationRun(request, `뺀 줄 알림 ${Date.now()}`)
  await page.route(`**/api/runs/${run.run_id}/actions/bulk`, async (route) => {
    const res = await route.fetch()
    const body = await res.json() as { confirmed: number; skipped: { judgment_id: number; reason: string }[] }
    body.confirmed -= 1
    body.skipped = [{ judgment_id: 0, reason: 'CHECK' }]
    await route.fulfill({ response: res, json: body })
  })
  await as(page, ENGINEER)
  await page.goto(`/#/reviews/${run.run_id}`)
  const unconfirmed = page.locator('#judge tbody tr').filter({ hasNot: page.locator('.cfm') })
  await unconfirmed.nth(0).getByRole('checkbox').check()
  await unconfirmed.nth(1).getByRole('checkbox').check()
  await page.locator('#judge .bulk').getByRole('button', { name: '제안대로 확정' }).click()
  await expect(page.getByRole('status').filter({ hasText: '판정 1건을 일괄 확정했습니다. 1건은 제외했습니다(검산 1). 개별 확인 후 확정하세요.' })).toBeVisible()
})
