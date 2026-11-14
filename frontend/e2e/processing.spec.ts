import { expect, test, type Page } from '@playwright/test'
import { ENGINEER, as, deviationRun } from './helpers'

// 명세 review-workspace "처리 상태 화면", "처리 중 목록 새로고침"의 Scenario
// (change update-review-screens, update-processing-progress).
// 합성 문서는 몇 초 만에 처리가 끝나므로, 실행 상태 응답 앞 몇 번을 "처리 중"으로 바꿔 보인다.

/** 실행 요약 응답 앞 left번을 patch로 바꾼다 (patch가 함수면 부를 때마다 새로 만든다) */
async function fakeProcessing(page: Page, runId: number, patch: Record<string, unknown> | (() => Record<string, unknown>),
  left = 2) {
  await page.route(`**/api/runs/${runId}`, async (route) => {
    if (route.request().method() !== 'GET' || left <= 0) return route.continue()
    left -= 1
    const res = await route.fetch()
    const body = await res.json()
    await route.fulfill({ response: res, json: { ...body, stage: 'PROCESSING', judgments: 0, ...(typeof patch === 'function' ? patch() : patch) } })
  })
}

const typing = (done: number) => ({ part: 'type', done, total: 3397, file_index: 1, file_count: 1 })

// Scenario: 처리 중
test('처리 중인 검토', async ({ page, request }) => {
  const run = await deviationRun(request, `처리 상태 ${Date.now()}`)
  await fakeProcessing(page, run.run_id, { step: 'risks', step_detail: null })
  await as(page, ENGINEER)
  await page.goto(`/#/reviews/${run.run_id}`)
  const bar = page.getByRole('progressbar', { name: 'RFP 분석' })
  await expect(bar).toBeVisible()
  const pct = Number(await bar.getAttribute('aria-valuenow'))
  expect(pct).toBeGreaterThan(0)
  expect(pct).toBeLessThan(100)
  await expect(page.locator('.ldtx').first()).toContainText('위험 조건 찾는 중')
  await expect(page.locator('.ldtx').first()).toContainText('문서 1개')
  await expect(page.getByRole('tab', { name: '판정' })).toBeVisible({ timeout: 15_000 })
  await expect(bar).toHaveCount(0)
})

test('유형 붙이기 진행', async ({ page, request }) => {
  const run = await deviationRun(request, `유형 붙이기 진행 ${Date.now()}`)
  let done = 0
  await fakeProcessing(page, run.run_id,
    () => ({ step: 'documents', step_detail: typing(done), step_updated_at: new Date().toISOString() }), 100)
  await as(page, ENGINEER)
  await page.goto(`/#/reviews/${run.run_id}`)
  const bar = page.getByRole('progressbar', { name: 'RFP 분석' })
  await expect(page.locator('.ldtx').first()).toContainText('AI로 유형 붙이는 중 0 / 3,397건')
  const zero = Number(await bar.getAttribute('aria-valuenow'))

  done = 480                                   // 화면이 2초마다 다시 부르면 바뀐 진행이 보인다
  await expect(page.locator('.ldtx').first()).toContainText('AI로 유형 붙이는 중 480 / 3,397건')
  await expect(page.locator('.ldtime')).toContainText('지난 시간')
  expect(Number(await bar.getAttribute('aria-valuenow'))).toBeGreaterThan(zero)
  await expect(page.getByText('10분 넘게 진행이 없습니다')).toHaveCount(0)
})

test('오래 진행이 없음', async ({ page, request }) => {
  const run = await deviationRun(request, `진행 없음 ${Date.now()}`)
  const before = new Date(Date.now() - 11 * 60 * 1000).toISOString()
  await fakeProcessing(page, run.run_id, { step: 'documents', step_detail: typing(40), step_updated_at: before }, 100)
  await as(page, ENGINEER)
  await page.goto(`/#/reviews/${run.run_id}`)
  await expect(page.getByRole('alert')).toContainText('10분 넘게 진행이 없습니다')
})

test('목록이 저절로 바뀜', async ({ page, request }) => {
  const run = await deviationRun(request, `목록 새로고침 ${Date.now()}`)
  let faking = true
  await page.route('**/api/runs?limit=*', async (route) => {
    const res = await route.fetch()
    const body = await res.json()
    if (!faking) return route.fulfill({ response: res, json: body })
    await route.fulfill({ response: res, json: body.map((r: { run_id: number }) => r.run_id === run.run_id
      ? { ...r, stage: 'PROCESSING', step: 'documents', step_detail: typing(480) } : r) })
  })
  await as(page, ENGINEER)
  await page.goto('/#/reviews')
  const row = page.getByRole('row').filter({ hasText: run.review_no })
  await expect(row).toContainText('처리 중')
  await expect(row).toContainText('%')
  faking = false                               // 이제 처리가 끝난 것처럼 실제 응답을 준다
  // 새로고침하지 않아도 5초 뒤 다시 불러 담당자 확인 상태로 바뀐다
  await expect(row).not.toContainText('처리 중', { timeout: 15_000 })
  await expect(row).toContainText('담당자 확인')
})

// 명세 review-workspace "처리 중 목록 새로고침" (change update-list-progress, 목업 v4.96 목록 줄 진행 막대)
test('목록 줄 진행 막대', async ({ page, request }) => {
  const [a, b] = [await deviationRun(request, `목록 막대 ${Date.now()}`), await deviationRun(request, `목록 멈춤 ${Date.now()}`)]
  const old = new Date(Date.now() - 15 * 60_000).toISOString()
  await page.route('**/api/runs?limit=*', async (route) => {
    const res = await route.fetch()
    const body = await res.json()
    await route.fulfill({ response: res, json: body.map((r: { run_id: number }) => r.run_id === a.run_id
      ? { ...r, stage: 'PROCESSING', step: 'documents', step_detail: typing(480), step_updated_at: new Date().toISOString() }
      : r.run_id === b.run_id ? { ...r, stage: 'PROCESSING', step: 'judge', step_detail: null, step_updated_at: old } : r) })
  })
  await as(page, ENGINEER)
  await page.goto('/#/reviews')
  const ra = page.getByRole('row').filter({ hasText: a.review_no })
  await expect(ra.getByRole('progressbar', { name: `${a.review_no} 진행` })).toBeVisible()
  await expect(ra.locator('.lprog-t')).toHaveText(/^1\/11 AI로 유형 붙이는 중 · \d+ %$/)
  await expect(ra.locator('.lprog')).not.toHaveClass(/warn/)
  const rb = page.getByRole('row').filter({ hasText: b.review_no })
  await expect(rb.locator('.lprog-t')).toHaveText(/^4\/11 제품과 비교해 판정하는 중 · \d+ %$/)
  await expect(rb.locator('.lprog')).toHaveClass(/warn/)
})
