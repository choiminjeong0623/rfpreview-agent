import { expect, test } from '@playwright/test'
import { ENGINEER, as, deviationRun, judgmentRun } from './helpers'

// 명세 review-workspace "판정 탭 지난 확정 표시"의 Scenario (change add-review-memory).
// 앞 검토에서 첫 판정을 일탈 후보로 고치고(deviationRun), 같은 문서로 새 검토를 돌린다. 계산은 백엔드 tests/test_review_memory.py.

test('지난 확정과 다른 줄 거르기', async ({ page, request }) => {
  const before = await deviationRun(request, `지난 확정 앞 ${Date.now()}`)
  const run = await judgmentRun(request, `지난 확정 뒤 ${Date.now()}`)
  await as(page, ENGINEER)
  await page.goto(`/#/reviews/${run.run_id}`)
  const chip = page.getByRole('button', { name: /지난 확정과 다름/ })
  await expect(chip).toBeVisible()
  await chip.click()
  await expect(chip).toHaveAttribute('aria-pressed', 'true')
  const rows = page.locator('#judge table.tbl tbody tr')
  await expect(rows.first()).toContainText('지난 확정과 다름')
  expect(await rows.count()).toBe(Number((await chip.locator('.n').textContent()) ?? '0'))
  // 공용 시험 DB에는 다른 시험이 고친 줄도 있어, 앞 검토에서 고친 줄을 화면과 같은 순서의 목록에서 찾는다
  type J = { past_decision: { run_id: number } | null }
  const list = await (await request.get(`/api/runs/${run.run_id}/judgments?past=differs&order=priority&limit=10`)).json() as J[]
  const at = list.findIndex((j) => j.past_decision?.run_id === before.run_id)
  expect(at).toBeGreaterThanOrEqual(0)
  await rows.nth(at).click()
  const past = page.locator('tr.pastrow').first()
  await expect(past).toContainText(before.review_no)
  await expect(past).toContainText('사유: 시험용 일탈')
  await expect(past).toContainText('지금과 다름')
})
