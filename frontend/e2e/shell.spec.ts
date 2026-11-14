import { expect, test } from '@playwright/test'

// 명세 review-workspace "앱 틀과 화면 주소"의 Scenario (change update-app-shell).
// 백엔드(8000)와 `npm run dev`(5173)만 있으면 되고 RFP 원문은 필요 없다.

test('메뉴로 화면 이동', async ({ page }) => {
  await page.goto('/#/reviews')
  const nav = page.getByRole('navigation', { name: '메뉴' })
  await expect(nav.getByRole('link', { name: 'RFP 검토' })).toHaveAttribute('aria-current', 'page')

  await nav.getByRole('button', { name: '지식 관리' }).click()
  await nav.getByRole('link', { name: '제품 관리' }).click()
  await expect(page).toHaveURL(/#\/products$/)
  await expect(nav.getByRole('link', { name: '제품 관리' })).toHaveAttribute('aria-current', 'page')
  await expect(page.getByRole('navigation', { name: '현재 위치' })).toContainText('기준 데이터')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('제품표')
  await expect(page.getByRole('navigation', { name: '현재 위치' }).getByRole('link', { name: '홈' })).toBeVisible()

  // 주소로 바로 열어도 같은 화면과 메뉴가 켜진다
  await page.goto('/#/todo')
  await expect(nav.getByRole('link', { name: '협조 요청' })).toHaveAttribute('aria-current', 'page')
  await expect(page.getByRole('button', { name: 'RFP 관리' })).toHaveAttribute('aria-expanded', 'true')
})

test('메뉴 접기', async ({ page }) => {
  await page.goto('/#/')
  await page.getByRole('button', { name: '메뉴 접기' }).click()
  await expect(page.locator('.app')).toHaveClass(/mini/)
  await page.reload()
  await expect(page.locator('.app')).toHaveClass(/mini/)   // 접은 상태를 기억한다
  await page.getByRole('button', { name: '메뉴 펼치기' }).click()
  await expect(page.locator('.app')).not.toHaveClass(/mini/)
})

test('사용자 바꾸기', async ({ page }) => {
  await page.goto('/#/reviews')
  const chip = page.getByRole('button', { name: '사용자 바꾸기' })
  await chip.click()
  await page.getByRole('button', { name: /기본 승인자/ }).click()
  await expect(chip).toContainText('기본 승인자')
  await expect(chip).toContainText('승인자')
  await page.reload()
  await expect(chip).toContainText('기본 승인자')   // 고른 사용자를 기억한다
})

test('알림은 예시로 보인다', async ({ page }) => {
  await page.goto('/#/reviews')
  await page.getByRole('button', { name: /알림 \d건/ }).click()
  const panel = page.getByRole('dialog', { name: '알림' })
  await expect(panel).toContainText('예시')
  await panel.getByRole('button', { name: '모두 읽음으로' }).click()
  await expect(page.getByRole('button', { name: '알림 0건' })).toBeVisible()
})
