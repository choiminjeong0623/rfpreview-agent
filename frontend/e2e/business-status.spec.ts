import { readFileSync } from 'node:fs'
import { expect, test, type APIRequestContext } from '@playwright/test'
import { as, dueIn, ENGINEER } from './helpers'

// 명세 review-workspace "사업 현황 화면", "사업 상세 화면", "검토 등록 사업 연결"의 Scenario (change add-project-status).
// 합성 문서(e2e/fixtures, 고객 원문 아님)를 API로 올려 실행을 만든다. 백엔드(8000)와 `npm run dev`(5173)가 필요하다.
const DOCX = new URL('./fixtures/synthetic_154kV_GIS_spec.docx', import.meta.url)

type Run = { run_id: number; review_no: string; business_id: number; business_no: string }

async function start(request: APIRequestContext, form: Record<string, string>): Promise<Run> {
  const res = await request.post('/api/runs', {
    multipart: {
      files: { name: 'synthetic_154kV_GIS_spec.docx', mimeType: 'application/octet-stream', buffer: readFileSync(DOCX) },
      // 문서 목록에 없는 문서라 묶음을 정해 보낸다 (reject-unjudged-registration)
      choices: JSON.stringify({ 'synthetic_154kV_GIS_spec.docx': { bundle: 'B' } }),
      actor_id: String(ENGINEER), due_date: dueIn(), ...form,
    },
  })
  expect(res.status()).toBe(202)
  const run = await res.json()
  await expect.poll(async () => (await (await request.get(`/api/runs/${run.run_id}`)).json()).stage,
    { timeout: 60_000 }).not.toBe('PROCESSING')
  return (await request.get(`/api/runs/${run.run_id}`)).json()
}

/** 합성 문서는 협조 요청을 만들어 "협조 대기"가 된다. 엔지니어가 요청을 보내고 회신 받음으로 표시해 "판정 확인"으로 둔다.
 *  백엔드에 메일 서버·부서 주소(RFP_SMTP_HOST, RFP_MAIL_*)가 설정되어 있어야 한다 (docker compose의 Mailpit) */
async function finishHelp(request: APIRequestContext, runId: number) {
  for (const role of ['COST', 'QUALITY', 'SALES']) {
    const tasks = await (await request.get(`/api/assignments?role=${role}`)).json() as { assignment_id: number; run_id: number }[]
    const mine = tasks.filter((x) => x.run_id === runId)
    if (!mine.length) continue
    const sent = await request.post(`/api/runs/${runId}/assignments/send`,
      { data: { assignment_ids: mine.map((t) => t.assignment_id), actor_id: ENGINEER } })
    expect((await sent.json()).sent).toBe(mine.length)
    for (const t of mine) {
      expect((await request.put(`/api/assignments/${t.assignment_id}`, { data: { status: 'DONE', actor_id: ENGINEER } })).ok()).toBe(true)
    }
  }
}

test('사업 현황 열기', async ({ page, request }) => {
  const name = `사업 현황 열기 ${Date.now()}`
  const run = await start(request, { new_business_name: name, review_name: '154 kV GIS' })
  await finishHelp(request, run.run_id)
  await as(page, ENGINEER)
  await page.goto('/#/projects')
  await expect(page.getByRole('note')).toHaveCount(0)                       // 예시 띠 없음
  const row = page.locator('a.pl-row', { hasText: name })
  await expect(row).toContainText('판정 확인')
  await expect(row).toContainText('엔지니어')
})

test('반려 칩', async ({ page, request }) => {
  const name = `반려 칩 ${Date.now()}`
  const run = await start(request, { new_business_name: name, review_name: '반려 범위' })
  // 반려 상태를 만드는 결재 흐름은 approval-flow.spec에서 본다. 여기서는 상신·반려를 API로 한다.
  const users = await (await request.get('/api/users')).json() as { user_id: number; role: string }[]
  const approver = users.find((u) => u.role === 'APPROVER')!.user_id
  const sent = await request.post(`/api/runs/${run.run_id}/finish-review`,
    { data: { approver_id: approver, comment: '시험 상신', actor_id: ENGINEER } })
  test.skip(sent.status() !== 200, '상신 조건(확인 안 한 줄 등)이 맞지 않아 반려를 만들 수 없습니다')
  await request.post(`/api/runs/${run.run_id}/approval`, { data: { decision: 'REJECTED', comment: '시험 반려', actor_id: approver } })
  await as(page, ENGINEER)
  await page.goto('/#/projects')
  const chip = page.locator('a.pl-row', { hasText: name }).locator('.pj-ch')
  await expect(chip).toHaveText('반려')
  await expect(chip).toHaveAttribute('title', /반려 범위 · /)
})

test('팀 전체', async ({ page, request }) => {
  const name = `팀 전체 ${Date.now()}`
  const users = await (await request.get('/api/users')).json() as { user_id: number; role: string }[]
  const cost = users.find((u) => u.role === 'COST')!.user_id
  await request.post('/api/businesses', { data: { business_name: name, actor_id: ENGINEER } })
  await as(page, cost)
  await page.goto('/#/projects')
  await expect(page.locator('a.pl-row', { hasText: name })).toHaveCount(0)
  await page.getByRole('button', { name: '팀 전체' }).click()
  await expect(page.locator('a.pl-row', { hasText: name })).toBeVisible()
})

test('범위 카드에서 검토로', async ({ page, request }) => {
  const run = await start(request, { new_business_name: `범위 카드 ${Date.now()}`, review_name: '카드 범위' })
  await finishHelp(request, run.run_id)
  await page.goto(`/#/projects/${run.business_no}`)
  await page.locator('a.pd-card', { hasText: '카드 범위' }).click()
  await expect(page).toHaveURL(new RegExp(`#/reviews/${run.run_id}$`))
})

test('이 사업에 RFP 등록', async ({ page, request }) => {
  const name = `RFP 등록 ${Date.now()}`
  const run = await start(request, { new_business_name: name, customer_name: '예시 고객사 등록' })
  await page.goto(`/#/projects/${run.business_no}`)
  await page.getByRole('link', { name: '이 사업에 RFP 등록' }).click()
  await expect(page).toHaveURL(new RegExp(`#/register/business/${run.business_id}$`))
  await page.locator('input[type=file]').setInputFiles({ name: 'a.docx', mimeType: 'application/octet-stream', buffer: readFileSync(DOCX) })
  // 문서 목록에 없는 문서라 묶음을 B로 정해야 다음으로 간다 (reject-unjudged-registration)
  await page.locator('tr', { hasText: 'a.docx' }).getByLabel('묶음').selectOption('B')
  await page.getByRole('button', { name: /다음/ }).click()
  await expect(page.getByRole('radio', { name: /진행 중인 사업에 추가/ })).toBeChecked()
  await expect(page.getByLabel('진행 중인 사업', { exact: true })).toHaveValue(String(run.business_id))
})

test('제출 완료 단추', async ({ page, request }) => {
  const run = await start(request, { new_business_name: `제출 단추 ${Date.now()}` })
  await page.goto(`/#/projects/${run.business_no}`)
  await expect(page.getByRole('button', { name: '제출 완료로 표시' })).toBeDisabled()
  await expect(page.getByText('연결된 검토가 모두 승인되어야 제출 완료로 표시할 수 있습니다.')).toBeVisible()
})

test('지난 이력은 예시', async ({ page, request }) => {
  const run = await start(request, { new_business_name: `지난 이력 ${Date.now()}` })
  await page.goto(`/#/projects/${run.business_no}`)
  await expect(page.getByRole('note')).toHaveCount(0)
  await page.getByRole('tab', { name: '지난 이력' }).click()
  await expect(page.getByRole('note').filter({ hasText: '예시 화면 · 실제 데이터와 연결되지 않음' })).toBeVisible()
})

test('사업 고르면 미리 채움', async ({ page, request }) => {
  const name = `미리 채움 ${Date.now()}`
  const made = await (await request.post('/api/businesses', { data: { business_name: name, customer_name: '예시 고객사 채움',
    country: '베트남', due_date: '2099-12-31', actor_id: ENGINEER } })).json() as { business_id: number }
  await page.goto('/#/register')
  await page.locator('input[type=file]').setInputFiles({ name: 'a.docx', mimeType: 'application/octet-stream', buffer: readFileSync(DOCX) })
  // 문서 목록에 없는 문서라 묶음을 B로 정해야 다음으로 간다 (reject-unjudged-registration)
  await page.locator('tr', { hasText: 'a.docx' }).getByLabel('묶음').selectOption('B')
  await page.getByRole('button', { name: /다음/ }).click()
  await page.getByRole('radio', { name: /진행 중인 사업에 추가/ }).check()
  await page.getByLabel('진행 중인 사업', { exact: true }).selectOption(String(made.business_id))
  await expect(page.getByRole('textbox', { name: '고객사', exact: true })).toHaveValue('예시 고객사 채움')
  await expect(page.getByRole('textbox', { name: '국가', exact: true })).toHaveValue('베트남')
  await expect(page.locator('input[type=date]')).toHaveValue('2099-12-31')
})

test('머리글에서 사업으로', async ({ page, request }) => {
  const run = await start(request, { new_business_name: `머리글 사업 ${Date.now()}` })
  await page.goto(`/#/reviews/${run.run_id}`)
  await page.getByTitle('사업 상세 보기').click()
  await expect(page).toHaveURL(new RegExp(`#/projects/${run.business_no}$`))
})
