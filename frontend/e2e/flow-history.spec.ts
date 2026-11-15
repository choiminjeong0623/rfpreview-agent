import { expect, test } from '@playwright/test'
import { ENGINEER, as, deviationRun } from './helpers'

// 명세 review-workspace "실행 기록의 흐름 기록"의 Scenario (change add-flow-history, C2 · update-runlog-fiori).

test('흐름 기록 펼치기', async ({ page, request }) => {
  const run = await deviationRun(request, `흐름 기록 ${Date.now()}`)
  const summary = await (await request.get(`/api/runs/${run.run_id}`)).json() as { judgments: number }
  await as(page, ENGINEER)
  await page.goto('/#/runlog')
  await page.locator('tr', { hasText: run.review_no }).first().click()       // 상세 화면으로 (update-runlog-detail)
  await expect(page).toHaveURL(new RegExp(`#/runlog/${run.run_id}$`))
  const steps = page.locator('#rl-steps')
  await expect(steps).toContainText(`판정 0 → ${summary.judgments}`)
  await expect(steps.locator('.rlstop')).toHaveText('담당자 확인에서 멈춤')
  await expect(steps.locator('table').getByRole('button')).toHaveCount(0)   // 보기만 한다
})

test('단계별 처리 한 표', async ({ page, request }) => {
  const run = await deviationRun(request, `단계 한 표 ${Date.now()}`)
  const summary = await (await request.get(`/api/runs/${run.run_id}`)).json() as { judgments: number }
  await as(page, ENGINEER)
  await page.goto(`/#/runlog/${run.run_id}`)
  const steps = page.locator('#rl-steps')
  await expect(steps.locator('tr', { hasText: '제품 비교 판정' })).toContainText(`판정 0 → ${summary.judgments}`)
  await expect(steps.locator('tr', { hasText: '담당자 전달' })).toBeVisible()
  await expect(page.getByText('흐름 저장 시각 기준')).toHaveCount(0)        // 두 번째 단계 목록 없음
  const top = (await page.locator('.rlkpi-top b').textContent())!.trim()
  await expect(steps.locator('tr.rltop')).toContainText(top)
  await expect(steps.locator('tr.rltop')).toContainText('가장 오래 걸림')
})
