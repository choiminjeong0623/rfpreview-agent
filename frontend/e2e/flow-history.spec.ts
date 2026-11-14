import { expect, test } from '@playwright/test'
import { ENGINEER, as, deviationRun } from './helpers'

// 명세 review-workspace "실행 기록의 흐름 기록"의 Scenario (change add-flow-history, C2).

test('흐름 기록 펼치기', async ({ page, request }) => {
  const run = await deviationRun(request, `흐름 기록 ${Date.now()}`)
  const summary = await (await request.get(`/api/runs/${run.run_id}`)).json() as { judgments: number }
  await as(page, ENGINEER)
  await page.goto('/#/runlog')
  await page.locator('tr', { hasText: run.review_no }).first().click()
  const flow = page.locator('.rlflow')
  await expect(flow).toContainText('흐름 기록')
  await expect(flow).toContainText(`판정 0 → ${summary.judgments}`)
  await expect(flow.locator('.rlstop')).toHaveText('담당자 확인에서 멈춤')
  await expect(flow.getByRole('button')).toHaveCount(0)                 // 보기만 한다
})
