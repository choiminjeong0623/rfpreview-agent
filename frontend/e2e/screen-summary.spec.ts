import { expect, test } from '@playwright/test'
import { ENGINEER, as, deviationRun } from './helpers'

// 명세 review-workspace "요약 상자"의 Scenario (change add-screen-summary, 결정 Q1).
// 문장 틀은 백엔드 tests/test_screen_summary.py. 여기서는 상자 모양·링크·홈 수 일치·실패 안내를 본다.

test('검토 상세 요약 상자', async ({ page, request }) => {
  const run = await deviationRun(request, `요약 상자 ${Date.now()}`)
  await as(page, ENGINEER)
  await page.goto(`/#/reviews/${run.run_id}`)
  const box = page.getByRole('region', { name: '검토 요약' })
  await expect(box.locator('.ais-h b')).toHaveText('요약')
  await expect(box.locator('.ais-tag')).toHaveText('자동 요약')
  await expect(box).toContainText(/꼭 볼 것 \d+줄은 일탈 후보 \d+건/)
  await expect(box.locator('.ais-m')).toContainText(/문서 1개에서 요구사항 \d+줄을 찾아 \d+줄 비교/)
  // 제목 줄 바로 아래 (정보 3묶음 위)
  await expect(page.locator('.ttl + .ais')).toBeVisible()
  // 먼저 볼 일탈 후보 링크 → 판정 상세
  const link = box.locator('.ais-p a').first()
  await link.click()
  await expect(page).toHaveURL(new RegExp(`#/reviews/${run.run_id}/judgments/\\d+`))
})

test('홈 요약 상자', async ({ page }) => {
  await as(page, ENGINEER)
  await page.goto('/#/')
  const mine = page.locator('.qsum button', { hasText: '내가 처리할 건' }).locator('b')
  await expect(mine).not.toHaveText('—')
  const box = page.getByRole('region', { name: '홈 요약' })
  await expect(box.locator('.ais-tag')).toHaveText('자동 요약')
  const n = await mine.textContent()
  await expect(box.locator('.ais-p')).toContainText(n === '0' ? '지금 내 차례인 검토는 없습니다.' : `내 차례인 검토는 ${n}건입니다.`)
})

// Scenario: 요약 실패
test('요약 실패와 다시 요약', async ({ page }) => {
  let fail = true
  await page.route('**/api/home/summary**', async (route) => {
    if (fail) return route.fulfill({ status: 500, json: { detail: '시험용 실패' } })
    return route.fulfill({ json: { sentences: [[{ t: '다시 쓴 요약입니다.', kind: 'text', href: null }]], meta: null,
      written_by: 'CODE', made_at: new Date().toISOString() } })
  })
  await as(page, ENGINEER)
  await page.goto('/#/')
  const box = page.getByRole('region', { name: '홈 요약' })
  await expect(box.getByRole('alert')).toContainText('요약을 만들지 못했습니다')
  fail = false
  await box.getByRole('button', { name: '다시 요약' }).click()
  await expect(box.locator('.ais-p')).toHaveText('다시 쓴 요약입니다.')
})
