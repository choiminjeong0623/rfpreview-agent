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
  await expect(page).toHaveURL(new RegExp(`#/runlog/${run.run_id}$`))     // 상세 화면으로 (update-runlog-detail)
  await expect(page.getByRole('heading', { name: `실행 기록 · ${run.review_no}` })).toBeVisible()
  const steps = page.locator('.rlopen')
  await expect(steps).toContainText('처음 처리')
  await expect(steps).toContainText('문서 읽기')
  await expect(steps).toContainText('제품 비교 판정')
})

// 명세 review-workspace "실행 기록 화면" (change update-runlog-detail)
test('실행 기록 상세에서 돌아가기', async ({ page, request }) => {
  const run = await deviationRun(request, `실행 기록 상세 ${Date.now()}`)
  await as(page, ENGINEER)
  await page.goto(`/#/runlog/${run.run_id}`)
  await page.getByRole('link', { name: '← 실행 기록' }).click()
  await expect(page).toHaveURL(/#\/runlog$/)
  await expect(page.getByRole('heading', { name: '실행 기록', exact: true })).toBeVisible()
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

// 명세 review-run "실행 기록 화면의 AI 호출" (change update-runlog-fiori). 호출 기록은 응답을 바꿔 화면만 본다.
test('거른 결과가 없을 때', async ({ page, request }) => {
  const run = await deviationRun(request, `AI 호출 거르기 ${Date.now()}`)
  const at = new Date().toISOString()
  const call = (id: number, step: string | null, role: string, ms: number) => ({
    call_id: id, feature: step ? 'analysis' : 'handoff', step, role, model: 'gemini-test', prompt_version: 'v1', attempt: 0,
    started_at: at, ended_at: at, duration_ms: ms, input_tokens: 10, output_tokens: 5, thinking_tokens: 0,
    result: 'OK', dropped_reason: null, input_hash: 'a'.repeat(16), output_hash: 'b'.repeat(16), batch_lines: 1 })
  await page.route(`**/api/runs/${run.run_id}/ai-calls`, (route) => route.fulfill({ json: {
    calls: [call(1, 'documents', 'label', 1200), call(2, null, 'handoff', 900)], count: 2,
    by_result: { OK: 2 }, step_ms: [{ step: 'documents', ms: 1200 }, { step: '—', ms: 900 }], different_answers: 0 } }))
  await as(page, ENGINEER)
  await page.goto(`/#/runlog/${run.run_id}`)
  const calls = page.locator('#rl-calls')
  await expect(calls).toContainText('분석 밖 (협조 요청·도우미 등)')
  await calls.getByLabel('단계 거르기').selectOption('documents')
  await calls.getByLabel('역할 거르기').selectOption('handoff')
  await expect(calls).toContainText('조건에 맞는 AI 호출이 없습니다')
  await expect(calls).toContainText('0 / 2건')
  await calls.getByRole('button', { name: '초기화' }).click()
  await expect(calls.locator('tbody tr')).toHaveCount(2)
  await expect(calls.getByRole('button', { name: '초기화' })).toHaveCount(0)
})
