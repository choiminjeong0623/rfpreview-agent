import { readFileSync } from 'node:fs'
import { expect, test } from '@playwright/test'
import { as, deviationRun, ENGINEER, exportItem } from './helpers'

// 명세 review-workspace "TBE 준수표 화면"의 Scenario (change add-tbe-export).

test('넣을 줄 바꾸기', async ({ page, request }) => {
  const run = await deviationRun(request, `TBE ${Date.now()}`)     // 판정 하나를 일탈로 고쳐 확정
  await as(page, ENGINEER)
  await page.goto(`/#/reviews/${run.run_id}`)
  await exportItem(page, 'TBE 준수표')
  await expect(page).toHaveURL(new RegExp(`#/reviews/${run.run_id}/tbe$`))
  await expect(page.getByRole('navigation', { name: '현재 위치' })).toContainText(run.review_no)
  const sum = page.getByLabel('요약')
  await expect(sum).toContainText(/포함 항목\s*\d{2}/)
  await expect(page.getByText(`TBE_${run.review_no}_후보포함.xlsx`)).toBeVisible()
  await page.getByRole('radio', { name: '확정 항목만' }).check()
  await expect(sum).toContainText(/포함 항목\s*1(?!\d)/)
  await expect(page.locator('table.tb-t tbody tr')).toHaveCount(1)
  await expect(page.locator('table.tb-t tbody tr')).toContainText('Deviation')
  await expect(page.getByText(`TBE_${run.review_no}_확정만.xlsx`)).toBeVisible()
  await expect(page.getByRole('option', { name: /제출본 v1/ })).toHaveAttribute('disabled', '')
})

test('엑셀 내려받기', async ({ page, request }) => {
  const run = await deviationRun(request, `TBE 받기 ${Date.now()}`)
  await page.goto(`/#/reviews/${run.run_id}/tbe`)
  await expect(page.locator('table.tb-t tbody tr').first()).toBeVisible()
  const wait = page.waitForEvent('download')
  await page.getByRole('button', { name: '엑셀 내려받기' }).click()
  const file = await wait
  // 헤드리스 Chromium은 blob 내려받기의 한글 파일 이름을 "download"로 줄 때가 있어, 이름은 알림으로 확인한다
  expect(readFileSync(await file.path()).subarray(0, 2).toString()).toBe('PK')       // xlsx(zip)
  const n = (await page.locator('table.tb-t tbody tr').count())
  await expect(page.getByRole('status')).toContainText(`TBE_${run.review_no}_후보포함.xlsx 를 내려받았습니다 (`)
  expect(n).toBeGreaterThan(0)
})
