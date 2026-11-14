import { readFileSync } from 'node:fs'
import { expect, test } from '@playwright/test'
import { APPROVER, ENGINEER, as, deviationRun } from './helpers'

// 명세 review-workspace "검토 상세 문서 표"의 문서 추가 Scenario (change add-document-addendum).
// 합성 데이터시트로 판정을 마친 검토(첫 줄은 일탈 후보로 수정)에 줄 하나를 더 확정하고,
// 합성 사양서(묶음 B)를 더해 다시 분석한다.

const ADD = 'synthetic_154kV_GIS_spec.docx'
type J = { judgment_id: number; requirement_id: number; value_id: number | null; product_code: string | null; review_status: string; result: string }
const key = (j: J) => `${j.requirement_id}-${j.value_id}-${j.product_code}`

test('문서 추가하고 다시 분석', async ({ page, request }) => {
  const run = await deviationRun(request, `문서 추가 ${Date.now()}`)
  const before = await (await request.get(`/api/runs/${run.run_id}/judgments?limit=500`)).json() as J[]
  const edited = before.find((j) => j.review_status === 'EDITED')!
  const other = before.find((j) => j.review_status === 'CANDIDATE')!
  const ok = await request.post(`/api/runs/${run.run_id}/actions`, {
    data: { target: 'judgment', target_id: other.judgment_id, action: 'CONFIRM', actor_id: ENGINEER },
  })
  expect(ok.status()).toBe(200)

  await as(page, ENGINEER)
  await page.goto(`/#/reviews/${run.run_id}`)
  await page.getByRole('button', { name: '문서 1개' }).click()
  const dialog = page.getByRole('dialog', { name: '문서 1개' })
  await expect(dialog.getByRole('heading', { name: '문서 추가' })).toBeVisible()
  await dialog.getByLabel('추가할 파일 (docx·PDF)').setInputFiles({
    name: ADD, mimeType: 'application/octet-stream',
    buffer: readFileSync(new URL(`./fixtures/${ADD}`, import.meta.url)),
  })
  const row = dialog.locator('.docadd tbody tr')
  await expect(row).toContainText(ADD)
  await row.getByLabel('묶음').selectOption('B')
  await expect(row).toContainText('판정 대상')
  await dialog.getByRole('button', { name: /추가하고 다시 분석/ }).click()
  await expect(dialog).toBeHidden()
  await expect(page.getByRole('button', { name: '문서 2개' })).toBeVisible({ timeout: 60_000 })

  const after = new Map(((await (await request.get(`/api/runs/${run.run_id}/judgments?limit=500`)).json()) as J[])
    .map((j) => [key(j), j]))
  expect(after.get(key(other))?.review_status).toBe('CONFIRMED')
  expect(after.get(key(edited))?.review_status).toBe('EDITED')
  expect(after.get(key(edited))?.result).toBe('DEVIATION_CANDIDATE')

  await page.getByRole('tab', { name: '이력' }).click()
  await expect(page.locator('#log table.mini tbody tr').first()).toContainText(`문서 추가: ${ADD}`)
})

test('승인자에게는 문서 추가 없음', async ({ page, request }) => {
  const run = await deviationRun(request, `문서 추가 승인자 ${Date.now()}`)
  await as(page, APPROVER)
  await page.goto(`/#/reviews/${run.run_id}`)
  await page.getByRole('button', { name: '문서 1개' }).click()
  const dialog = page.getByRole('dialog', { name: '문서 1개' })
  await expect(dialog.locator('tbody tr')).toHaveCount(1)
  await expect(dialog.getByRole('heading', { name: '문서 추가' })).toHaveCount(0)
})
