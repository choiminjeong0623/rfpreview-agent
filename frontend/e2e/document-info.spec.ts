import { expect, test, type Route } from '@playwright/test'
import { ENGINEER, as, deviationRun } from './helpers'

// 명세 review-workspace "검토 상세 문서 표"의 Scenario (change update-document-info).
// 합성 데이터시트(묶음 A)로 판정을 마친 검토를 쓰고, 묶음 C만 있는 경우는 문서 응답을 바꿔 만든다.

test('판정 묶음 보기', async ({ page, request }) => {
  const run = await deviationRun(request, `문서 표 ${Date.now()}`)
  await as(page, ENGINEER)
  await page.goto(`/#/reviews/${run.run_id}`)
  await expect(page.getByRole('button', { name: '문서 1개' })).toBeVisible()
  await expect(page.locator('.hf', { hasText: '제출 마감' })).toContainText('묶음 A')
})

test('문서 표 열기', async ({ page, request }) => {
  const run = await deviationRun(request, `문서 표 ${Date.now()}`)
  await as(page, ENGINEER)
  await page.goto(`/#/reviews/${run.run_id}`)
  await page.getByRole('button', { name: '문서 1개' }).click()
  const dialog = page.getByRole('dialog', { name: '문서 1개' })
  const row = dialog.locator('tbody tr')
  await expect(row).toHaveCount(1)
  await expect(row).toContainText('synthetic_judgment.docx')
  await expect(row.locator('td').nth(3)).toHaveText(/^(규칙|AI)$/)          // 규칙이 종류를 못 정하면 AI가 보조한다
  await expect(row.locator('td').nth(4)).toHaveText('묶음 A')
  await expect(row).toContainText('판정 대상')
  await expect(row.locator('td').nth(6)).toHaveText(/^\d[\d,]*$/)
  await page.keyboard.press('Escape')
  await expect(dialog).toBeHidden()
})

test('판정하지 않는 문서', async ({ page, request }) => {
  const run = await deviationRun(request, `문서 표 ${Date.now()}`)
  await page.route(/\/api\/runs\/\d+\/documents$/, async (r: Route) => {
    const docs = await (await r.fetch()).json() as Record<string, unknown>[]
    await r.fulfill({ json: docs.map((d) => ({ ...d, bundle: 'C', judge_target: false, needs_review: true })) })
  })
  await as(page, ENGINEER)
  await page.goto(`/#/reviews/${run.run_id}`)
  await expect(page.locator('.hf', { hasText: '제출 마감' }).locator('.c-red')).toHaveText('판정 문서 없음')
  await page.getByRole('button', { name: '문서 1개' }).click()
  const row = page.getByRole('dialog').locator('tbody tr')
  await expect(row).toHaveClass(/skip/)
  await expect(row).toContainText('판정 안 함')
  await expect(row).toContainText('묶음 C: 판정 범위 밖')
  await expect(row).toContainText('확인 필요')
})
