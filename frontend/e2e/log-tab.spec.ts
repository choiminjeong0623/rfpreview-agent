import { expect, test } from '@playwright/test'
import { ENGINEER, as, deviationRun, riskRun } from './helpers'

// 명세 review-workspace "이력 탭"의 Scenario (change update-review-screens).

test('판정 바꾼 이력', async ({ page }) => {
  const run = await deviationRun(page.request, `이력 판정 ${Date.now()}`)
  await as(page, ENGINEER)
  await page.goto(`/#/reviews/${run.run_id}`)
  await page.getByRole('tab', { name: '이력' }).click()
  const rows = page.locator('#log table.mini tbody tr')
  await expect(rows.first()).toContainText(/판정 ".+" .+ → 일탈 후보/)
  await expect(rows.first()).toContainText('사유: 시험용 일탈')
  await expect(rows.last()).toContainText(/시스템판정 \d+건 생성/)
})

test('위험 조건 닫은 이력', async ({ page }) => {
  const run = await riskRun(page.request, `이력 위험 ${Date.now()}`)
  const risks = await (await page.request.get(`/api/runs/${run.run_id}/risks`)).json() as { risk_id: number; risk_kind: string; expression: string | null }[]
  const blanket = risks.find((r) => r.risk_kind === 'BLANKET')!
  const res = await page.request.post(`/api/runs/${run.run_id}/actions`, {
    data: { target: 'risk_flag', target_id: blanket.risk_id, action: 'REJECT', reason: '일반 조항이라 문제 없음', actor_id: ENGINEER },
  })
  expect(res.status()).toBe(200)
  await as(page, ENGINEER)
  await page.goto(`/#/reviews/${run.run_id}`)
  await page.getByRole('tab', { name: '이력' }).click()
  const first = page.locator('#log table.mini tbody tr').first()
  await expect(first).toContainText(`위험 조건 "${blanket.expression}" 문제 없음으로 닫음`)
  await expect(first).toContainText('사유: 일반 조항이라 문제 없음')
})
