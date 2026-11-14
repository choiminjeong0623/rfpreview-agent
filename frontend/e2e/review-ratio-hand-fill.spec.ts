import { expect, test } from '@playwright/test'
import { ENGINEER, as, deviationRun } from './helpers'

// 명세 review-workspace "검토 상세 요약 칸과 탭"의 Scenario "직접 작성할 칸 표시" (change update-review-ratio-hand-fill).
// 합성 데이터시트에는 제품표에 연결되지 않은 빈칸이 없어서, 승인 화면 응답의 직접 작성할 칸 수만 3으로 바꿔 화면을 본다.
// 계산(빈칸을 비율에서 빼기)은 백엔드 tests/test_review_ratio_hand_fill.py에서 본다.

test('직접 작성할 칸 표시', async ({ page, request }) => {
  const run = await deviationRun(request, `직접 작성할 칸 ${Date.now()}`)
  await page.route(`**/api/runs/${run.run_id}/approval`, async (route) => {
    const res = await route.fetch()
    const body = await res.json()
    body.review_ratio.hand_fill = 3
    await route.fulfill({ response: res, json: body })
  })
  await as(page, ENGINEER)
  await page.goto(`/#/reviews/${run.run_id}`)
  // 확인 필요 비율은 v4.96부터 결재 상신 창에만 있다 (update-detail-header). AR-03 줄에 뺀 칸 수를 적는다
  await page.getByRole('button', { name: '결재 상신' }).click()
  await expect(page.getByRole('dialog', { name: '결재 상신' })).toContainText('직접 작성할 칸 3개는 뺌')
})
