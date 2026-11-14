import { expect, test } from '@playwright/test'
import { fileURLToPath } from 'node:url'

// 명세 review-workspace "PDF 올리기"의 Scenario (change add-pdf-input).
// e2e/fixtures/synthetic_judgment.pdf는 synthetic_judgment.docx와 같은 데이터시트를 PDF로 만든 것 (문서 목록 묶음 A).
const PDF = new URL('./fixtures/synthetic_judgment.pdf', import.meta.url)
const isoAfter = (days: number) => new Date(Date.now() + days * 86_400_000).toISOString().slice(0, 10)

test('PDF로 검토 등록', async ({ page, request }) => {
  await page.goto('/#/register')
  await page.getByLabel('파일 올리기').setInputFiles(fileURLToPath(PDF))
  const row = page.locator('tr', { hasText: 'synthetic_judgment.pdf' })
  await expect(row.getByLabel('묶음')).toHaveValue('A', { timeout: 10_000 })    // 분류 추천에 PDF가 보임
  await expect(row).toContainText('판정 대상')
  await page.getByRole('button', { name: /다음/ }).click()
  await page.getByLabel('설비 범위', { exact: true }).fill(`PDF 등록 ${Date.now()}`)
  await page.getByLabel('제출 마감일').fill(isoAfter(10))
  await page.getByRole('button', { name: /다음/ }).click()
  await page.getByRole('button', { name: /등록하고 분석 시작/ }).click()
  const done = page.getByRole('status').filter({ hasText: /RV-\d{4}-\d{3}/ })   // 등록 진행 줄도 status라 검토 번호 줄을 기다린다
  const reviewNo = (await done.textContent())!.match(/RV-\d{4}-\d{3}/)![0]
  const runs = await (await request.get('/api/runs?limit=50')).json() as { run_id: number; review_no: string }[]
  const run = runs.find((r) => r.review_no === reviewNo)!
  await expect.poll(async () => (await (await request.get(`/api/runs/${run.run_id}`)).json()).stage,
    { timeout: 60_000 }).toBe('ENGINEER_REVIEW')
  const summary = await (await request.get(`/api/runs/${run.run_id}`)).json() as { judgments: number }
  expect(summary.judgments).toBeGreaterThan(0)                                       // PDF 표로 판정까지
})

// 명세 document-intake "PDF 원문 위치의 쪽 번호" Scenario "PDF 요구사항의 쪽"의 화면 쪽 (add-pdf-page-location)
test('PDF 판정 원문 위치에 쪽', async ({ page }) => {
  const loc = { file_no: 101, section_no: '1', section_title: 'GENERAL', table_name: null, item_no: null,
    line_start: 12, line_end: 12, page: 2 }
  await page.route('**/api/runs/*/judgments?*', async (r) => {
    const res = await r.fetch()
    const rows = await res.json() as { locations: unknown[] }[]
    return r.fulfill({ response: res, json: rows.map((j) => ({ ...j, locations: [loc] })) })
  })
  const runs = await (await page.request.get('/api/runs?limit=50')).json() as { run_id: number }[]
  let id = 0                                                    // 판정이 있는 검토 하나 (위치는 위에서 바꿔 끼움)
  for (const r of runs) {
    const s = await (await page.request.get(`/api/runs/${r.run_id}`)).json() as { judgments: number }
    if (s.judgments > 0) { id = r.run_id; break }
  }
  expect(id).toBeGreaterThan(0)
  await page.goto(`/#/reviews/${id}`)
  await expect(page.locator('#judge table.tbl tbody tr').first()).toContainText('2쪽 · 1 GENERAL · 12행')
  await page.unrouteAll({ behavior: 'ignoreErrors' })
})
