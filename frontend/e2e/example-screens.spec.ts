import { expect, test } from '@playwright/test'

// 명세 review-workspace "예시 화면"의 Scenario (change add-example-screens).
// 예시 데이터만 쓰므로 RFP 원문이나 실행 데이터가 없어도 된다.

const BAND = '예시 화면 · 실제 데이터와 연결되지 않음'

test('예시 띠', async ({ page }) => {
  const calls: string[] = []
  // 머리글 분석 진행 표시(update-header-progress)는 모든 화면에서 실행 목록(/api/runs?limit=)을 부르므로 뺀다
  page.on('request', (r) => { if (r.url().includes('/api/runs') && !r.url().includes('/api/runs?limit=')) calls.push(r.url()) })
  await page.goto('/#/')
  const nav = page.getByRole('navigation', { name: '메뉴' })
  await nav.getByRole('button', { name: 'RFP 관리' }).click()   // 홈에서는 목업처럼 묶음이 모두 접혀 있다
  await nav.getByRole('link', { name: '입찰 이력' }).click()
  await expect(page).toHaveURL(/#\/bids$/)
  await expect(page.getByRole('note').filter({ hasText: BAND })).toBeVisible()
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('입찰 이력')
  await expect(page.locator('tbody tr').first()).toBeVisible()
  calls.length = 0
  await page.getByRole('button', { name: /전체/ }).first().click()
  expect(calls).toEqual([])

  // 다른 예시 화면도 같은 띠를 보인다
  for (const path of ['/phrases', '/team', '/notice', '/sysnotice', '/files', '/settings']) {
    await page.goto('/#' + path)
    await expect(page.getByRole('note').filter({ hasText: BAND })).toBeVisible()
  }
  expect(calls).toEqual([])
})

test('저장하지 않음', async ({ page }) => {
  await page.goto('/#/notice')
  const unread = page.getByTitle('읽지 않음')
  const before = await unread.count()
  expect(before).toBeGreaterThan(0)
  await page.locator('button.bp-row').filter({ has: unread }).first().click()
  await expect(unread).toHaveCount(before - 1)

  await page.goto('/#/settings')
  const first = page.locator('label.stck input[type=checkbox]').first()
  await expect(first).toBeChecked()
  await first.uncheck()
  await page.getByRole('button', { name: '저장' }).click()
  await expect(page.getByRole('status')).toContainText('저장하지 않습니다')

  // 다른 화면에 갔다 오면 처음 상태
  await page.goto('/#/')
  await page.goto('/#/settings')
  await expect(page.locator('label.stck input[type=checkbox]').first()).toBeChecked()
  await page.goto('/#/notice')
  await expect(page.getByTitle('읽지 않음')).toHaveCount(before)
})

test('금액 가림', async ({ page }) => {
  await page.goto('/#/bids')
  const amounts = page.locator('tbody tr td:last-child')
  await expect(amounts.first()).toContainText('영업 권한 필요')
  await expect(amounts.filter({ hasText: /\d/ })).toHaveCount(0)

  await page.locator('tbody tr').first().click()
  await expect(page).toHaveURL(/#\/bids\/.+/)
  await expect(page.getByText('가격 평가')).toBeVisible()
  await expect(page.getByTitle('영업 권한 필요').first()).toBeVisible()
})

test('로그인 화면', async ({ page }) => {
  await page.goto('/#/login')
  await expect(page.getByRole('navigation', { name: '메뉴' })).toHaveCount(0)
  await page.getByRole('button', { name: '로그인', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('입력하지 않은 칸이 있습니다')
  await page.getByLabel('사번 또는 회사 이메일').fill('20261234')
  await page.getByLabel('비밀번호', { exact: true }).fill('example')
  await page.getByRole('button', { name: '로그인', exact: true }).click()
  await expect(page).toHaveURL(/#\/$/, { timeout: 10_000 })
  await expect(page.getByRole('navigation', { name: '메뉴' })).toBeVisible()
})
