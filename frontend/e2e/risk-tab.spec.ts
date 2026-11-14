import { expect, test, type Page } from '@playwright/test'
import { ENGINEER, as, riskRun } from './helpers'

// 명세 review-workspace "위험 조건 탭"의 Scenario (change update-review-screens).
// "사람이 찾은 특이 요구"는 실제 제안이 되어 e2e/rule-suggestion.spec.ts에서 본다 (add-rule-suggestion).

async function openRisk(page: Page, name: string) {
  const run = await riskRun(page.request, `${name} ${Date.now()}`)
  await as(page, ENGINEER)
  await page.goto(`/#/reviews/${run.run_id}`)
  await page.getByRole('tab', { name: '위험 조건' }).click()
  return page.locator('#risk table.mini > tbody > tr')
}

test('위험 조건 건수', async ({ page }) => {
  const rows = await openRisk(page, '위험 건수')
  await expect(page.locator('#risk .sech .note')).toHaveText('포괄 조항 1 · 값 불일치 1 · 범위 모호 1')
  await expect(rows).toHaveCount(3)
  await expect(rows.locator('td:first-child .st')).toHaveText(['후보', '후보', '후보'])
  await expect(rows.locator('td.loc button').first()).toContainText('행')
  await expect(rows.filter({ hasText: '가스 누설률' })).toHaveCount(1)
})

test('문제 없음으로 닫기', async ({ page }) => {
  const rows = await openRisk(page, '위험 닫기')
  const row = rows.filter({ hasText: '가스 누설률' })
  await row.getByRole('button', { name: '문제 없음' }).click()
  await row.getByLabel('문제 없음 사유').fill('적용 대상이 달라 문제 없음')
  await row.getByRole('button', { name: '닫기' }).click()
  await expect(rows.last()).toHaveClass('dis')
  await expect(rows.last().locator('.st')).toHaveText('문제 없음')
  await expect(rows.last()).toContainText('적용 대상이 달라 문제 없음')
  await expect(rows.last().locator('td').last()).toContainText('·')
  await expect(page.locator('#risk .sech .note')).toContainText('값 불일치 0')
})

test('사유 없이 닫기', async ({ page }) => {
  const rows = await openRisk(page, '위험 사유')
  const row = rows.filter({ hasText: '가스 누설률' })
  await row.getByRole('button', { name: '문제 없음' }).click()
  await expect(row.getByRole('button', { name: '닫기' })).toBeDisabled()
  await row.getByLabel('문제 없음 사유').fill('  ')
  await expect(row.getByRole('button', { name: '닫기' })).toBeDisabled()
})

test('위험으로 확정', async ({ page }) => {
  const rows = await openRisk(page, '위험 확정')
  const row = rows.filter({ hasText: '“deemed”' })
  await row.getByRole('button', { name: '위험으로 확정' }).click()
  await expect(row.locator('.st')).toHaveText('확정')
  await expect(row.locator('td').last()).not.toContainText('위험으로 확정')
  await expect(row.locator('td').last()).toContainText('·')
})

// 명세 review-workspace "위험 조건 처리 알림"의 Scenario (change update-risk-action-toasts)
test('위험으로 확정 알림', async ({ page }) => {
  const rows = await openRisk(page, '확정 알림')
  const row = rows.filter({ hasText: '“deemed”' })
  await row.getByRole('button', { name: '위험으로 확정' }).click()
  const toast = page.locator('.uisnk').filter({ hasText: '“deemed”: 위험으로 확정했습니다' })
  await expect(toast).toContainText('질의 후보와 결재 확인 사유에 남습니다')
  await expect(row.locator('.st')).toHaveText('확정')
})

test('문제 없음 알림', async ({ page }) => {
  const rows = await openRisk(page, '닫기 알림')
  const row = rows.filter({ hasText: '“deemed”' })
  await row.getByRole('button', { name: '문제 없음' }).click()
  await row.getByLabel('문제 없음 사유').fill('책임 범위가 계약서에 정해져 있음')
  await row.getByRole('button', { name: '닫기' }).click()
  const toast = page.locator('.uisnk').filter({ hasText: '“deemed”: 문제 없음으로 닫았습니다' })
  await expect(toast).toContainText('질의 후보는 목록에서 빠집니다')
  await expect(rows.filter({ hasText: '“deemed”' }).locator('.st')).toHaveText('문제 없음')
})
