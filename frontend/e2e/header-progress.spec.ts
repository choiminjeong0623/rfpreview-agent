import { expect, test, type Page } from '@playwright/test'

// 명세 review-workspace "머리글 분석 진행 표시"·"분석 끝남 안내" Scenario (change update-header-progress).
// 실행 목록 응답(GET /api/runs)을 테스트가 정한 값으로 바꿔, 처리 중 검토를 만들지 않고 머리글만 본다.

const now = () => new Date().toISOString()
const run = (stage: string) => ({
  run_id: 9001, review_no: 'RV-TEST-01', review_name: '머리글 시험 검토', project_name: null, customer_name: null, country: null,
  due_date: null, engineer_id: 1, engineer_name: '시험 엔지니어', business_id: null, business_no: null,
  stage, step: stage === 'PROCESSING' ? 'documents' : 'assign',
  step_detail: stage === 'PROCESSING' ? { part: 'type', done: 480, total: 3397, file_index: 1, file_count: 1 } : null,
  step_updated_at: now(), failed_step: null, error_message: null, started_at: now(), finished_at: null,
  files: 'synthetic.docx', requirements: 0, risks: 0, deviation_candidates: 0, proposals: 0,
  approver_id: null, approver: null, requested_by_id: null, requested_by: null, requested_at: null, decision: null, decided_at: null,
})

async function runs(page: Page, body: () => unknown[]) {
  await page.route(/\/api\/runs\?limit=/, (r) => r.fulfill({ json: body() }))
}

test('머리글 분석 진행 표시', async ({ page }) => {
  await runs(page, () => [run('PROCESSING')])
  await page.goto('/#/dev/ui')
  const btn = page.getByRole('banner').getByRole('button', { name: /분석 1건 · \d+ %/ })
  await expect(btn).toBeVisible()
  await btn.click()
  const pop = page.getByRole('dialog', { name: '분석 진행' })
  await expect(pop).toContainText('RV-TEST-01')
  await expect(pop).toContainText('AI로 유형 붙이는 중 480 / 3,397건')
  await expect(pop.getByRole('progressbar', { name: 'RV-TEST-01 진행' })).toBeVisible()
  await expect(pop.getByRole('link', { name: '진행 보기' })).toHaveAttribute('href', '#/reviews/9001')
})

test('처리 중 없으면 숨김', async ({ page }) => {
  await runs(page, () => [run('ENGINEER_REVIEW')])
  await page.goto('/#/dev/ui')
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  await expect(page.getByRole('banner').getByRole('button', { name: /분석 \d+건/ })).toHaveCount(0)
})

test('끝남 안내', async ({ page }) => {
  // 처음 3초는 처리 중, 그 뒤는 끝남 (개발 모드 StrictMode는 첫 요청을 두 번 보내 횟수로 나누지 않는다)
  const start = Date.now()
  await runs(page, () => [run(Date.now() - start < 3_000 ? 'PROCESSING' : 'ENGINEER_REVIEW')])
  await page.goto('/#/dev/ui')
  await expect(page.getByRole('banner').getByRole('button', { name: /분석 1건/ })).toBeVisible()
  // 처리 중이 있는 동안 5초마다 다시 부르고, 끝나면 단추가 사라지고 알림이 쌓인다
  const note = page.locator('.uitw .uit').filter({ hasText: '분석이 끝났습니다' })
  await expect(note).toBeVisible({ timeout: 10_000 })
  await expect(page.getByRole('banner').getByRole('button', { name: /분석 \d+건/ })).toHaveCount(0)
  await note.getByRole('link', { name: '판정 확인' }).click()
  await expect(page).toHaveURL(/#\/reviews\/9001$/)
})
