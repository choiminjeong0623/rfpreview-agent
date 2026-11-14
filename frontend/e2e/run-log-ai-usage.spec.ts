import { expect, test, type Page } from '@playwright/test'

// 명세 review-workspace "실행 기록의 AI 사용량"의 Scenario (change update-run-log-ai-usage).
// AI 사용량 응답은 page.route로 정해 두고 화면만 본다(AI를 부르지 않는다). 실행 표는 실제 백엔드 그대로.

type Row = Record<string, unknown>
const row = (day: string, feature: string, feature_name: string, calls: number, cost: number | null): Row => ({
  day, feature, feature_name, model: 'gemini-3.8-flash', calls, retries: 0,
  input_tokens: calls * 100, output_tokens: calls * 20, thinking_tokens: calls * 50, estimated_cost_krw: cost,
})

async function mock(page: Page, byDays: Record<number, { items: Row[]; total_calls: number; total_cost_krw: number | null }>) {
  const asked: number[] = []
  await page.route('**/api/ai-usage?*', (r) => {
    const days = Number(new URL(r.request().url()).searchParams.get('days'))
    asked.push(days)
    const body = byDays[days] ?? { items: [], total_calls: 0, total_cost_krw: 0 }
    return r.fulfill({ json: { days, ...body } })
  })
  return asked
}

const MONTH = {
  items: [row('2026-10-20', 'ANALYSIS', '분석', 22, 103), row('2026-11-02', 'ASSISTANT', '검토 도우미', 3, 4), row('2026-11-02', 'ANALYSIS', '분석', 482, 1309)],
  total_calls: 507, total_cost_krw: 1416,
}

test('AI 사용량 보기', async ({ page }) => {
  const asked = await mock(page, { 30: MONTH })
  await page.goto('/#/runlog')
  const box = page.locator('section.aiu')
  await expect(box.getByRole('group', { name: 'AI 사용량 기간' }).getByRole('button', { name: '30일' })).toHaveAttribute('aria-pressed', 'true')
  await expect(box.getByTestId('ai-usage-sum')).toContainText('호출 507회')
  await expect(box.getByTestId('ai-usage-sum')).toContainText('추정 비용 1,416원')
  await expect(box.getByTestId('ai-usage-sum').locator('.tag')).toHaveText('팀 가정')
  await expect(box).toContainText('실제 청구 금액은 Google 결제 화면에서 확인합니다.')
  const rows = box.locator('table tbody tr')
  await expect(rows).toHaveCount(3)
  await expect(rows.locator('td:first-child')).toHaveText(['2026-11-02', '2026-11-02', '2026-10-20'])   // 날짜 최신순
  await expect(rows.filter({ hasText: '검토 도우미' })).toContainText('300 / 60 / 150')
  expect([...new Set(asked)]).toEqual([30])                    // 개발 모드는 두 번 부를 수 있어 값만 본다
  await page.unrouteAll({ behavior: 'ignoreErrors' })
})

test('기간 바꾸기', async ({ page }) => {
  const asked = await mock(page, { 30: MONTH, 7: { items: [MONTH.items[1], MONTH.items[2]], total_calls: 485, total_cost_krw: 1313 } })
  await page.goto('/#/runlog')
  const box = page.locator('section.aiu')
  await expect(box.locator('table tbody tr')).toHaveCount(3)
  await box.getByRole('button', { name: '7일' }).click()
  await expect(box.getByRole('button', { name: '7일' })).toHaveAttribute('aria-pressed', 'true')
  await expect(box.locator('table tbody tr')).toHaveCount(2)
  await expect(box.getByTestId('ai-usage-sum')).toContainText('호출 485회')
  expect([...new Set(asked)]).toEqual([30, 7])                 // 30일로 열고 7일로 다시 부름
  await page.unrouteAll({ behavior: 'ignoreErrors' })
})

test('기능으로 거르기', async ({ page }) => {
  await mock(page, { 30: MONTH })
  await page.goto('/#/runlog')
  const box = page.locator('section.aiu')
  const chip = box.getByRole('group', { name: 'AI 사용 기능' }).getByRole('button', { name: /검토 도우미/ })
  await expect(chip).toContainText('1')
  await chip.click()
  await expect(chip).toHaveAttribute('aria-pressed', 'true')
  await expect(box.locator('table tbody tr')).toHaveCount(1)
  await expect(box.locator('table tbody tr')).toContainText('검토 도우미')
  await page.unrouteAll({ behavior: 'ignoreErrors' })
})

test('AI 사용 기록 없음', async ({ page }) => {
  await mock(page, { 30: { items: [], total_calls: 0, total_cost_krw: 0 } })
  await page.goto('/#/runlog')
  const box = page.locator('section.aiu')
  const empty = box.getByText('이 기간에 AI를 쓴 기록이 없습니다.')
  await expect(empty).toBeVisible()
  await expect(empty).toHaveClass(/dimv/)                         // 중립색
  await expect(box.getByTestId('ai-usage-sum')).toContainText('호출 0회')
  await expect(box.locator('table')).toHaveCount(0)
  await page.unrouteAll({ behavior: 'ignoreErrors' })
})

test('단가 모름', async ({ page }) => {
  await mock(page, { 30: { items: [row('2026-11-02', 'ASSISTANT', '검토 도우미', 2, null)], total_calls: 2, total_cost_krw: null } })
  await page.goto('/#/runlog')
  const box = page.locator('section.aiu')
  await expect(box.getByTestId('ai-usage-sum')).toContainText('추정 비용 단가 모름')
  await expect(box.getByTestId('ai-usage-sum').locator('.tag')).toHaveCount(0)
  await expect(box.locator('table tbody tr')).toContainText('단가 모름')
  await page.unrouteAll({ behavior: 'ignoreErrors' })
})
