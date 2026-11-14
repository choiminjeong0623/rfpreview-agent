import { expect, test } from '@playwright/test'
import { APPROVER, COMMENT, ENGINEER, as, deviationRun } from './helpers'

// 명세 review-workspace "판단 동작"·"내 할 일 화면"의 Scenario (change update-approval-flow). 준비는 helpers.ts.

test('결재 상신 창', async ({ page, request }) => {
  const run = await deviationRun(request, `결재 상신 창 ${Date.now()}`)
  await as(page, ENGINEER)
  await page.goto(`/#/reviews/${run.run_id}`)
  await page.getByRole('button', { name: '결재 상신' }).click()
  const dialog = page.getByRole('dialog', { name: '결재 상신' })
  await expect(dialog.locator('.apck li').first()).toContainText(`일탈 후보 ${run.deviations}건`)  // 지금 걸리는 AR-01
  await expect(dialog.getByLabel('결재자')).toHaveValue(String(APPROVER))               // 승인자가 1명이면 미리 고름
  const send = dialog.getByRole('button', { name: '결재 상신' })
  await expect(send).toBeDisabled()                                                      // 의견 전에는 눌리지 않는다
  await dialog.getByLabel('상신 의견').fill(COMMENT)
  await expect(send).toBeEnabled()
  await send.click()
  await expect(page.getByText('기본 승인자의 결재를 기다리고 있습니다')).toBeVisible()
  await expect(page.locator('.wop')).toContainText(COMMENT)
  // 결정 전 상신 취소 → 바로 검토 상세 판정 탭으로 돌아간다
  await page.getByRole('button', { name: '상신 취소' }).click()
  await expect(page.locator('.uisnk')).toContainText('상신을 취소했습니다.')
  await expect(page.getByRole('button', { name: '결재 상신' })).toBeEnabled()
})

test('승인 화면', async ({ page, request }) => {
  const run = await deviationRun(request, `승인 화면 ${Date.now()}`)
  const sent = await request.post(`/api/runs/${run.run_id}/finish-review`,
    { data: { approver_id: APPROVER, comment: COMMENT, actor_id: ENGINEER } })
  expect(sent.status()).toBe(200)
  await as(page, APPROVER)
  await page.goto(`/#/reviews/${run.run_id}`)
  await expect(page.getByText('결재할 검토입니다')).toBeVisible()
  await expect(page.locator('.wop')).toContainText(COMMENT)                              // 상신 의견
  const checks = page.locator('.wck')
  await expect(checks).toContainText(`일탈 후보 ${run.deviations}건`)                     // 걸린 기준, 일탈 후보 수
  await expect(checks).toContainText(/일탈 목록에 \d+건/)                                  // 목록에 들어간 수
  await expect(checks).toContainText(/목록에 (빠진 일탈 없음|없는 일탈 \d+건)/)              // 빠진 일탈
  const reject = page.getByRole('button', { name: '반려' })
  await expect(reject).toBeDisabled()                                                    // 반려에는 의견이 필요하다
  await page.getByLabel('결재 의견').fill('일탈 사유를 보완할 것')
  await reject.click()
  await expect(page.locator('.ttl1')).toContainText('반려됨')                              // 제목 옆 단계 (v4.96)
})

test('엔지니어·승인자의 내 할 일', async ({ page, request }) => {
  const name = `내 할 일 결재 ${Date.now()}`
  const run = await deviationRun(request, name)
  await request.post(`/api/runs/${run.run_id}/finish-review`,
    { data: { approver_id: APPROVER, comment: COMMENT, actor_id: ENGINEER } })
  const mine = await (await request.get(`/api/tasks?user_id=${APPROVER}`)).json()
  const card = mine.reviews.find((c: { run_id: number }) => c.run_id === run.run_id)
  expect(card.criteria.map((c: { ar_code: string }) => c.ar_code)).toContain('AR-01')
  expect(card.approval.request_comment).toBe(COMMENT)
  // 승인자 카드는 홈(SCR-03)에 보인다. 협조 요청 화면(SCR-13)은 부서별 요청만 보인다
  await as(page, APPROVER)
  await page.goto(`/#/reviews/${run.run_id}`)
  await expect(page.getByText('결재할 검토입니다')).toBeVisible()
})
