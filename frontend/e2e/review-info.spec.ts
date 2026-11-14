import { readFileSync } from 'node:fs'
import { expect, test, type APIRequestContext } from '@playwright/test'
import { fileURLToPath } from 'node:url'

// 명세 review-workspace "검토 정보 입력과 표시"의 Scenario (change add-review-info).
// 합성 문서(e2e/fixtures, 고객 원문 아님)를 API로 올려 실행을 만든다. 백엔드(8000)와 `npm run dev`(5173)가 필요하다.
const DOCX = new URL('./fixtures/synthetic_154kV_GIS_spec.docx', import.meta.url)

function isoAfter(days: number): string {
  const d = new Date()
  d.setDate(d.getDate() + days)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

async function start(request: APIRequestContext, form: Record<string, string>) {
  const res = await request.post('/api/runs', {
    multipart: {
      files: { name: 'synthetic_154kV_GIS_spec.docx', mimeType: 'application/octet-stream', buffer: readFileSync(DOCX) },
      // 문서 목록에 없는 문서라 묶음을 정해 보낸다 (reject-unjudged-registration)
      choices: JSON.stringify({ 'synthetic_154kV_GIS_spec.docx': { bundle: 'B' } }),
      due_date: isoAfter(14), ...form,
    },
  })
  expect(res.status()).toBe(202)
  const run = await res.json()
  // 처리가 끝날 때까지 기다린다 (합성 문서라 몇 초)
  await expect.poll(async () => (await (await request.get(`/api/runs/${run.run_id}`)).json()).stage,
    { timeout: 60_000 }).not.toBe('PROCESSING')
  return run as { run_id: number; review_no: string }
}

test('목록에서 마감 보기', async ({ page, request }) => {
  const scope = `제어·보호반 ${Date.now()}`
  const run = await start(request, { project_name: 'Long An', review_name: scope, customer_name: '예시 송전회사',
    due_date: isoAfter(3), actor_id: '1' })
  await page.goto('/#/reviews')
  await page.getByRole('button', { name: '팀 전체' }).click()
  const row = page.locator('tr', { hasText: scope })
  await expect(row).toContainText(run.review_no)
  await expect(row).toContainText('Long An')
  await expect(row).toContainText('예시 송전회사')
  await expect(row).toContainText('기본 엔지니어')
  await expect(row).toContainText('D-3')
  await expect(row.locator('td.num')).toHaveCount(5)          // 순번 + 요구사항·위험·일탈·제안
})

test('검토명이 빈 검토', async ({ page, request }) => {
  const run = await start(request, {})
  await page.goto('/#/reviews')
  await page.getByRole('button', { name: '팀 전체' }).click()
  const row = page.locator('tr', { hasText: run.review_no })
  await expect(row).toContainText('synthetic_154kV_GIS_spec.docx')    // 검토명 자리에 첫 파일 이름
  await expect(row.locator('td').nth(4)).toContainText('D-14')         // 마감 자리에 D-day (update-due-required)
})

test('머리글에서 고치기', async ({ page, request }) => {
  const run = await start(request, { review_name: '머리글 고치기 확인', actor_id: '1' })
  await page.goto(`/#/reviews/${run.run_id}`)
  await expect(page.getByRole('navigation', { name: '현재 위치' })).toContainText(run.review_no)
  await page.getByRole('button', { name: '검토 정보 수정' }).click()
  const dialog = page.getByRole('dialog', { name: '검토 정보 수정' })
  await dialog.getByLabel('고객사').fill('새 고객사')
  await dialog.getByRole('button', { name: '저장' }).click()
  await expect(dialog).toBeHidden()
  await expect(page.getByRole('definition').filter({ hasText: '새 고객사' })).toBeVisible()   // 사업 상자 고객사 (v4.96)
  await page.getByRole('tab', { name: '이력' }).click()
  await expect(page.locator('#log')).toContainText('검토 정보 고침: 고객사 비어 있음 → 새 고객사')   // 이력 탭 문장 (SCR-08-9)
  await page.goto('/#/reviews')
  await page.getByRole('button', { name: '팀 전체' }).click()
  await expect(page.locator('tr', { hasText: run.review_no })).toContainText('새 고객사')
})

test('검토 등록 화면으로 시작', async ({ page }) => {
  await page.goto('/#/register')
  await page.getByLabel('파일 올리기').setInputFiles(fileURLToPath(DOCX))
  await expect(page.getByText('올릴 준비')).toBeVisible()
  // 문서 목록에 없는 문서라 묶음을 B로 정해야 다음으로 간다 (reject-unjudged-registration)
  await page.locator('tr', { hasText: 'synthetic_154kV_GIS_spec.docx' }).getByLabel('묶음').selectOption('B')
  await page.getByRole('button', { name: /다음/ }).click()
  await expect(page.getByRole('button', { name: /다음/ })).toBeDisabled()     // 제출 마감일은 필수
  await page.getByLabel('새 사업명').fill('새만금 산단')     // 사업 연결: 새 사업 만들기 (add-project-status)
  await page.getByLabel('설비 범위', { exact: true }).fill('154 kV 송변전 설비')
  await page.getByLabel('제출 마감일').fill(isoAfter(10))
  await page.getByRole('button', { name: /다음/ }).click()
  await page.getByRole('button', { name: /등록하고 분석 시작/ }).click()
  await expect(page.getByRole('status')).toContainText(/RV-\d{4}-\d{3} 등록했습니다/)
})

// 명세 review-workspace "검토 등록 진행 표시" (change update-register-progress)
test('검토 등록 진행 표시', async ({ page }) => {
  // 큰 RFP처럼 서버가 늦게 답하게 한다 (요청은 실제로 보내 검토를 만든다)
  await page.route('**/api/runs', async (route) => {
    if (route.request().method() !== 'POST') return route.fallback()
    const res = await route.fetch()
    await new Promise((ok) => setTimeout(ok, 2500))
    await route.fulfill({ response: res })
  })
  await page.goto('/#/register')
  await page.getByLabel('파일 올리기').setInputFiles(fileURLToPath(DOCX))
  await expect(page.getByText('올릴 준비')).toBeVisible()
  await page.locator('tr', { hasText: 'synthetic_154kV_GIS_spec.docx' }).getByLabel('묶음').selectOption('B')
  await page.getByRole('button', { name: /다음/ }).click()
  await page.getByLabel('제출 마감일').fill(isoAfter(10))
  await page.getByRole('button', { name: /다음/ }).click()
  await page.getByRole('button', { name: /등록하고 분석 시작/ }).click()
  const bar = page.getByRole('progressbar', { name: '검토 등록 진행' })
  await expect(bar).toBeVisible()
  await expect(page.locator('.regprog')).toContainText(/파일 올리는 중|검토를 만드는 중/)
  await expect(page.getByRole('status').filter({ hasText: /RV-\d{4}-\d{3} 등록했습니다/ })).toBeVisible({ timeout: 15_000 })
  await expect(bar).toHaveCount(0)
  await page.unrouteAll({ behavior: 'ignoreErrors' })
})
