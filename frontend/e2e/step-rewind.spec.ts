import { expect, test } from '@playwright/test'
import { ENGINEER, as, deviationRun, openTab } from './helpers'

// 명세 review-workspace "이력 탭의 단계부터 다시 처리"의 Scenario (change add-step-rewind, C2).

test('이력 탭에서 다시 처리', async ({ page, request }) => {
  const run = await deviationRun(request, `되돌리기 ${Date.now()}`)
  await as(page, ENGINEER)
  await page.goto(`/#/reviews/${run.run_id}`)
  await openTab(page, '이력')
  await page.getByLabel('단계부터 다시 처리', { exact: true }).selectOption('judge')
  const go = page.getByRole('button', { name: '다시 처리' })
  await expect(go).toBeDisabled()                                        // 사유가 비면 못 누름
  await page.getByLabel('다시 처리하는 사유').fill('판정 규칙을 고쳐서')
  await go.click()
  await expect.poll(async () => (await (await request.get(`/api/runs/${run.run_id}`)).json()).stage,
    { timeout: 60_000 }).toBe('ENGINEER_REVIEW')
  await expect(page.locator('#log')).toContainText('제품 비교 판정부터 다시 처리', { timeout: 30_000 })
  await expect(page.locator('#log')).toContainText('사유: 판정 규칙을 고쳐서')
})
