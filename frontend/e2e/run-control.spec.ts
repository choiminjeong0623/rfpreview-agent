import { expect, test } from '@playwright/test'
import { ENGINEER, as, deviationRun } from './helpers'

// 명세 review-workspace "처리 상태 화면"·"분석 실패 화면"의 취소·다시 시도 Scenario (change add-run-control).
// 합성 문서는 몇 초 만에 끝나 처리 중에 누를 수 없으므로, 실행 요약 응답을 바꿔 보이고 취소·다시 시도 요청이 가는지 본다.
// 취소·다시 시도의 실제 처리는 백엔드 tests/test_run_control.py가 확인한다.

test('처리 중 분석 취소', async ({ page, request }) => {
  const run = await deviationRun(request, `분석 취소 ${Date.now()}`)
  let state: 'processing' | 'cancelling' | 'cancelled' = 'processing'
  let cancelBody: unknown = null
  await page.route(`**/api/runs/${run.run_id}`, async (route) => {
    const res = await route.fetch()
    const body = await res.json()
    const at = new Date().toISOString()
    const patch = state === 'cancelled'
      ? { stage: 'FAILED', failed_step: 'documents', error_message: '기본 엔지니어가 분석을 취소했습니다.', cancel_requested_at: at, retryable: true, judgments: 0 }
      : { stage: 'PROCESSING', step: 'documents', step_detail: null, step_updated_at: at, judgments: 0, cancel_requested_at: state === 'cancelling' ? at : null }
    await route.fulfill({ response: res, json: { ...body, ...patch } })
  })
  await page.route(`**/api/runs/${run.run_id}/cancel`, async (route) => {
    cancelBody = route.request().postDataJSON()
    state = 'cancelling'
    await route.fulfill({ json: {} })
  })
  await as(page, ENGINEER)
  await page.goto(`/#/reviews/${run.run_id}`)
  await page.getByRole('button', { name: '분석 취소' }).click()
  await expect(page.getByText('분석을 멈출까요?')).toBeVisible()
  await page.getByRole('button', { name: '취소하기' }).click()
  await expect(page.getByRole('status')).toContainText('취소하는 중')
  expect(cancelBody).toEqual({ actor_id: ENGINEER })
  state = 'cancelled'
  await expect(page.locator('.falert')).toContainText('문서 읽기 단계에서 취소했습니다', { timeout: 10_000 })
  await expect(page.locator('.fid')).toContainText('취소함')
})

test('실패 화면에서 다시 시도', async ({ page, request }) => {
  const run = await deviationRun(request, `다시 시도 ${Date.now()}`)
  let failed = true
  let retried = false
  await page.route(`**/api/runs/${run.run_id}`, async (route) => {
    if (!failed) return route.continue()                        // 다시 시도 뒤에는 실제 응답 (담당자 확인)
    const res = await route.fetch()
    const body = await res.json()
    await route.fulfill({ response: res, json: { ...body, stage: 'FAILED', failed_step: 'documents', judgments: 0,
      error_message: '기본 엔지니어가 분석을 취소했습니다.', cancel_requested_at: new Date().toISOString(), retryable: true } })
  })
  await page.route(`**/api/runs/${run.run_id}/retry`, async (route) => {
    retried = true
    failed = false
    await route.fulfill({ status: 202, json: {} })
  })
  await as(page, ENGINEER)
  await page.goto(`/#/reviews/${run.run_id}`)
  const card = page.locator('.fcard', { hasText: '어떻게 계속할까요' })
  await expect(card.getByRole('radio', { name: /다시 시도/ })).toBeChecked()
  await card.getByRole('button', { name: '다시 시도' }).click()
  await expect.poll(() => retried).toBe(true)
  await expect(page.getByRole('tab').first()).toBeVisible()      // 처리 상태를 지나 검토 상세로 바뀐다
})
