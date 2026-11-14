import { expect, test } from '@playwright/test'
import { ENGINEER, as, riskRun } from './helpers'

// 명세 review-workspace "검토 도우미 창"의 Scenario (change add-review-assistant, update-assistant-panel).
// e2e 백엔드는 AI 키 없이 돈다. 그때 도우미는 질문 글자로 찾은 근거 줄만 보인다(답 문장은 백엔드 가짜 AI 테스트에서 본다).

test('도우미에 묻기', async ({ page }) => {
  const run = await riskRun(page.request, `도우미 ${Date.now()}`)
  await as(page, ENGINEER)
  await page.goto(`/#/reviews/${run.run_id}`)
  await page.getByRole('button', { name: '검토 도우미' }).click()
  const panel = page.getByRole('dialog', { name: '검토 도우미' })
  await panel.getByLabel('검토 도우미 질문').fill('ambient temperature')
  await panel.getByRole('button', { name: '묻기' }).click()
  const rows = panel.getByTestId('assistant-evidence')
  await expect(rows.first()).toBeVisible()
  await expect(rows.filter({ hasText: 'The maximum ambient temperature for the GIS enclosure' })).toHaveCount(1)
  await expect(rows.first().locator('.as-loc')).toContainText('synthetic_154kV_GIS_spec.docx')
  await expect(panel.locator('.as-mode')).toHaveText(/^(AI 답변 \(근거와 대조함\)|검색어로 찾은 결과)/)
  await expect(panel.getByRole('heading', { name: /근거 조항 \d+건/ })).toBeVisible()
  await panel.getByText('찾은 방법 보기').click()
  await expect(panel.locator('.as-steps li').first()).toContainText('요구사항에서')
  await expect(panel.getByRole('button', { name: /확정|수정|반려|저장/ })).toHaveCount(0)   // 고치기 단추 없음
  await page.keyboard.press('Escape')
  await expect(panel).toHaveCount(0)
})

test('맞는 조항이 없을 때', async ({ page }) => {
  const run = await riskRun(page.request, `도우미 0건 ${Date.now()}`)
  await as(page, ENGINEER)
  await page.goto(`/#/reviews/${run.run_id}`)
  await page.getByRole('button', { name: '검토 도우미' }).click()
  const panel = page.getByRole('dialog', { name: '검토 도우미' })
  await panel.getByLabel('검토 도우미 질문').fill('시험 입회 조건이 있는 조항')
  await panel.getByRole('button', { name: '묻기' }).click()
  await expect(panel.locator('.as-none')).toContainText('일치하는 조항이 없습니다.')
  await expect(panel.locator('.as-none')).toContainText('영어 낱말로 찾아 보세요')
  await expect(panel.getByTestId('assistant-evidence')).toHaveCount(0)
})
