import { expect, test, type Page } from '@playwright/test'
import { APPROVER, ENGINEER, as, deviationRun, readRun } from './helpers'

// 명세 review-workspace "문서 읽기 점검 탭"·"상신 전 확인의 문서 읽기 점검"의 Scenario (change update-review-screens).

async function openRead(page: Page, name: string, user = ENGINEER) {
  const run = await readRun(page.request, `${name} ${Date.now()}`)
  await as(page, user)
  await page.goto(`/#/reviews/${run.run_id}`)
  await page.getByRole('tab', { name: '문서 읽기 점검' }).click()
  return page.locator('#read table.rdt > tbody > tr')
}

test('점검 줄 확인', async ({ page }) => {
  const rows = await openRead(page, '점검 확인')
  await expect(page.locator('#read .sech .note')).toHaveText('표 1 · 그림 1 · 단위 1 · 위치 1')
  await expect(rows).toHaveCount(4)
  await expect(rows.locator('.rdk')).toHaveText([/표$/, /그림$/, /단위$/, /위치$/])
  await expect(page.locator('#read .sech > .st')).toHaveText('확인 안 함 4건')
  await expect(page.getByRole('tab', { name: '문서 읽기 점검' }).locator('.tabn')).toHaveText('4')
  const fig = rows.filter({ hasText: 'Fig. 1 Single Line Diagram' })
  await expect(fig).toContainText('synthetic_read.docx')
  await fig.getByRole('button', { name: '직접 확인함' }).click()
  await expect(fig).toHaveClass('done')
  await expect(fig.locator('.rdok .st')).toHaveText('확인함')
  await expect(fig.locator('.rdok .en')).toContainText(' · ')
  await expect(page.locator('#read .sech > .st')).toHaveText('확인 안 함 3건')
  await expect(page.getByRole('tab', { name: '문서 읽기 점검' }).locator('.tabn')).toHaveText('3')
  await page.getByRole('tab', { name: '이력' }).click()
  await expect(page.locator('#log')).toContainText('문서 읽기 점검 확인: Fig. 1 Single Line Diagram')
})

test('점검 확인 되돌리기', async ({ page }) => {
  const rows = await openRead(page, '점검 되돌리기')
  const unit = rows.filter({ hasText: '단위를 모름' })
  await unit.getByRole('button', { name: '직접 확인함' }).click()
  await expect(page.locator('#read .sech > .st')).toHaveText('확인 안 함 3건')
  await unit.getByRole('button', { name: '되돌리기' }).click()
  await expect(unit.getByRole('button', { name: '직접 확인함' })).toBeVisible()
  await expect(unit).not.toHaveClass('done')
  await expect(page.locator('#read .sech > .st')).toHaveText('확인 안 함 4건')
})

test('고칠 수 없을 때 확인 단추', async ({ page }) => {
  const rows = await openRead(page, '점검 잠김', APPROVER)
  const button = rows.first().getByRole('button', { name: '직접 확인함' })
  await expect(button).toBeDisabled()
  await expect(rows.first().locator('[title]')).toHaveAttribute('title', '엔지니어만 확인할 수 있습니다')
})

test('상신 창의 점검 미확인', async ({ page }) => {
  await openRead(page, '점검 상신')
  await page.getByRole('tab', { name: '판정' }).click()
  await page.getByRole('button', { name: '결재 상신' }).click()
  const dialog = page.getByRole('dialog', { name: '결재 상신' })
  const line = dialog.locator('.apck li').filter({ hasText: '문서 읽기 점검 미확인 4건' })
  await expect(line).toHaveCount(1)
  await expect(line.locator('.apic')).toHaveClass(/warn/)
  await expect(line).toContainText('빠진 요구사항이 있을 수 있습니다')
})

test('읽지 못한 곳이 없는 검토', async ({ page }) => {
  // 합성 데이터시트(synthetic_judgment.docx)는 표 머리글이 분명하고 그림·단위 빠진 값·절 번호 문제가 없어 점검 줄이 0개다
  const run = await deviationRun(page.request, `점검 0줄 ${Date.now()}`)
  await as(page, ENGINEER)
  await page.goto(`/#/reviews/${run.run_id}`)
  const tab = page.getByRole('tab', { name: '문서 읽기 점검' })
  await tab.click()
  const read = page.locator('#read')
  await expect(read.locator('.rdempty')).toContainText('모든 문서를 끝까지 읽었습니다')
  await expect(read.locator('.rdempty')).toContainText('직접 확인할 곳이 없습니다')
  await expect(read.locator('table.rdt')).toHaveCount(0)
  await expect(read.locator('.rdi')).toHaveCount(0)
  await expect(read.locator('.sech > .st')).toHaveText('읽지 못한 곳 없음')
  await expect(read.locator('.sech .note')).toHaveText('표 0 · 그림 0 · 단위 0 · 위치 0')
  await expect(tab.locator('.tabn')).toHaveCount(0)
})

// 명세 review-workspace "검토 상세 탭 쪽 나누기"의 Scenario (change update-detail-tab-paging)
test('상세 탭 쪽 나누기', async ({ page }) => {
  // 점검 줄 4개를 15개로 늘려 돌려준다(줄 열쇠만 바꿈)
  await page.route(/\/api\/runs\/\d+\/read-checks$/, async (route) => {
    const res = await route.fetch()
    const base = (await res.json()) as { key: string }[]
    const many = Array.from({ length: 15 }, (_, i) => ({ ...base[i % base.length], key: `${base[i % base.length].key}-${i}` }))
    await route.fulfill({ response: res, json: many })
  })
  const rows = await openRead(page, '점검 쪽 나누기')
  const read = page.locator('#read')
  await expect(rows).toHaveCount(10)
  await expect(read.locator('.pager')).toContainText('1–10 / 전체 15건')
  await expect(read.locator('.sech > .st')).toHaveText('확인 안 함 15건')
  await read.locator('.pager').getByRole('button', { name: '2', exact: true }).click()
  await expect(rows).toHaveCount(5)
  await expect(read.locator('.pager')).toContainText('11–15 / 전체 15건')
  await page.unrouteAll({ behavior: 'ignoreErrors' })
})

test('짧은 목록은 쪽 번호 없음', async ({ page }) => {
  await openRead(page, '이력 짧음')
  await page.getByRole('tab', { name: '이력' }).click()
  const log = page.locator('#log')
  await expect(log.locator('table.mini tr').last()).toContainText('판정')
  const n = await log.locator('table.mini tr').count()
  expect(n).toBeLessThanOrEqual(10)
  await expect(log.locator('.pager')).toHaveCount(0)
  await expect(page.locator('#read .pager')).toHaveCount(0)
})
