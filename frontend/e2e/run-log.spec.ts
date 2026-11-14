import { expect, test } from '@playwright/test'
import { ENGINEER, as, deviationRun } from './helpers'

// 명세 review-workspace "실행 기록 화면"의 Scenario (change add-run-log). 합성 문서로 실제 실행을 만든다.

test('실행 기록 보기', async ({ page, request }) => {
  const run = await deviationRun(request, `실행 기록 ${Date.now()}`)
  await as(page, ENGINEER)
  await page.goto('/#/runlog')
  await expect(page.getByRole('heading', { name: '실행 기록' })).toBeVisible()
  await expect(page.locator('.kpis')).toContainText('추정 · 팀 가정')
  const row = page.locator('tr', { hasText: run.review_no })
  await expect(row).toContainText('담당자 확인')
  await expect(row).toContainText('규칙 기반')                         // 로컬은 AI 키 없이 돈다
  await row.click()
  const steps = page.locator('.rlopen')
  await expect(steps).toContainText('처음 처리')
  await expect(steps).toContainText('문서 읽기')
  await expect(steps).toContainText('제품 비교 판정')
  await row.click()
  await expect(steps).toHaveCount(0)
})

// 명세 service-health "AI 방식 표시" (change add-ai-mode): 실행 기록 머리 줄에 지금 AI 방식과 외부 전송 여부
test('실행 기록에 AI 방식 한 줄', async ({ page, request }) => {
  const health = await (await request.get('/api/health')).json()
  await as(page, ENGINEER)
  await page.goto('/#/runlog')
  const line = page.getByTestId('ai-mode')
  await expect(line).toBeVisible()
  await expect(line).toContainText(health.external_send ? '외부 AI로 보냅니다' : '보내지 않')
})
