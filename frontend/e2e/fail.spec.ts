import { expect, test, type Page } from '@playwright/test'
import { ENGINEER, as, deviationRun } from './helpers'

// 명세 review-workspace "분석 실패 화면"의 Scenario (change update-review-screens).
// 합성 문서는 실패하지 않으므로 실행 상태 응답을 "위험 조건 찾기에서 실패"로 바꿔 보인다. 문서 목록은 실제 응답.

const ERROR = '언어 모델이 응답하지 않았습니다 (3회 재시도 실패)'

async function openFailed(page: Page, name: string) {
  const run = await deviationRun(page.request, `${name} ${Date.now()}`)
  await page.route(`**/api/runs/${run.run_id}`, async (route) => {
    const res = await route.fetch()
    const body = await res.json()
    await route.fulfill({ response: res, json: { ...body, stage: 'FAILED', step: 'risks', failed_step: 'risks', error_message: ERROR, risks: 0, judgments: 0 } })
  })
  await as(page, ENGINEER)
  await page.goto(`/#/reviews/${run.run_id}`)
  return run
}

test('분석 실패 상세', async ({ page }) => {
  const run = await openFailed(page, '분석 실패')
  await expect(page.locator('.fid')).toContainText(run.review_no)
  await expect(page.locator('.fid .st')).toHaveText('처리 실패')
  const alert = page.locator('.falert')
  await expect(alert).toContainText('위험 조건 찾기 단계에서 멈췄습니다')
  await expect(alert).toContainText(ERROR)
  const steps = page.locator('.fsteps li')
  await expect(steps).toHaveCount(5)
  await expect(steps.nth(0)).toHaveClass('done')
  await expect(steps.nth(1)).toHaveClass('fail')
  await expect(steps.nth(2)).toHaveClass('wait')
  await expect(steps.nth(4)).toHaveClass('wait')
  await expect(page.locator('.ffiles')).toContainText('synthetic_judgment.docx')
  await expect(page.locator('.ftech')).toContainText('risks')
  await expect(page.getByRole('tab')).toHaveCount(0)
})

test('계속하는 방법 예시', async ({ page }) => {
  await openFailed(page, '실패 예시')
  const card = page.locator('.fcard', { hasText: '어떻게 계속할까요' })
  await expect(card.getByRole('note')).toHaveCount(0)              // 다시 시도는 실제로 처리한다 (add-run-control)
  await card.getByRole('radio', { name: /남은 부분은 직접 확인/ }).check()
  await expect(card.getByRole('note')).toContainText('예시 화면')
  await card.getByRole('button', { name: '남은 부분은 직접 확인' }).click()
  await expect(page.getByRole('status')).toHaveText(/예시 화면이라 처리하지 않았습니다/)
  await expect(page.locator('.fid .st')).toHaveText('처리 실패')
})
