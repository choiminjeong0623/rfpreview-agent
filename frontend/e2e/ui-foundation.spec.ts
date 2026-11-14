import { expect, test } from '@playwright/test'

// 명세 review-workspace 공통 부품 Scenario (change add-ui-foundation).
// 부품 견본 화면(#/dev/ui)은 지어낸 견본만 쓰므로 RFP 원문이나 실행 데이터가 없어도 된다.

test.beforeEach(async ({ page }) => { await page.goto('/#/dev/ui') })

// Scenario: 순번이 이어짐
test('쪽을 넘겨도 순번이 이어짐', async ({ page }) => {
  const table = page.getByRole('table', { name: '견본 목록' })
  await expect(table.locator('thead th').first()).toHaveText('순번')
  await expect(table.locator('tbody tr')).toHaveCount(10)
  await expect(table.locator('tbody tr td.sq').first()).toHaveText('1')
  await page.getByRole('button', { name: '2', exact: true }).click()
  await expect(table.locator('tbody tr')).toHaveCount(2)
  await expect(table.locator('tbody tr td.sq').first()).toHaveText('11')
})

test('빈 목록', async ({ page }) => {
  const table = page.getByRole('table', { name: '빈 목록' })
  await expect(table.locator('tbody tr')).toHaveCount(1)
  await expect(table.locator('tbody')).toHaveText('조건에 맞는 줄이 없습니다.')
})

// Scenario: 알림 쌓기
test('알림 두 개', async ({ page }) => {
  await page.getByRole('button', { name: '성공 알림 1' }).click()
  await page.getByRole('button', { name: '성공 알림 2' }).click()
  const toasts = page.locator('.uitw .uit')
  await expect(toasts).toHaveCount(2)
  await expect(toasts.nth(0)).toContainText('첫 번째 알림입니다')
  await expect(toasts.nth(1)).toContainText('두 번째 알림입니다')
  const [a, b] = [await toasts.nth(0).boundingBox(), await toasts.nth(1).boundingBox()]
  expect(a!.y).toBeLessThan(b!.y)
})

test('오류 알림은 남음', async ({ page }) => {
  await page.getByRole('button', { name: '오류 알림' }).click()
  const alert = page.locator('.uitw .uit.error')
  await expect(alert).toBeVisible()
  await page.waitForTimeout(5_000)
  await expect(alert).toBeVisible()
  await alert.getByRole('button', { name: '닫기' }).click()
  await expect(alert).toHaveCount(0)
})

// Scenario: 알림 쌓기 / 동작 결과는 아래 가운데 (change update-action-toast-place)
test('동작 결과는 아래 가운데', async ({ page }) => {
  await page.getByRole('button', { name: '동작 결과 1' }).click()
  await page.getByRole('button', { name: '동작 결과 2' }).click()
  const snack = page.locator('.uisnk')
  await expect(snack).toHaveCount(1)
  await expect(snack).toContainText('두 번째 동작 결과입니다')
  await expect(page.locator('.uitw')).toHaveCount(0)                    // 오른쪽 위 쌓기에는 없다
  const box = (await snack.boundingBox())!
  const view = page.viewportSize()!
  expect(Math.abs(box.x + box.width / 2 - view.width / 2)).toBeLessThan(4)   // 가운데
  expect(box.y + box.height).toBeGreaterThan(view.height - 80)                // 아래
  await expect(snack).toHaveCount(0, { timeout: 6_000 })                       // 4초 뒤 사라짐
})

test('잠긴 단추에 이유', async ({ page }) => {
  const btn = page.getByRole('button', { name: '승인', exact: true })
  await expect(btn).toBeDisabled()
  await expect(btn).toHaveAttribute('title', '승인자만 결정할 수 있습니다')
  await expect(btn).toHaveAccessibleDescription('승인자만 결정할 수 있습니다')
})

test('Esc로 창 닫기', async ({ page }) => {
  const opener = page.getByRole('button', { name: '견본 창 열기' })
  await opener.click()
  const dlg = page.getByRole('dialog', { name: '견본 창' })
  await expect(dlg).toBeVisible()
  await expect(dlg.getByLabel('사유')).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(dlg).toHaveCount(0)
  await expect(opener).toBeFocused()
})
