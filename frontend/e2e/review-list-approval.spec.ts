import { expect, test } from '@playwright/test'
import { APPROVER, COMMENT, ENGINEER, as, deviationRun } from './helpers'

// 명세 review-workspace "검토 목록 내가 올린 결재 보기"·"결재 대기 칸으로 거르기"(update-list-summary-filter)의 Scenario
// (change update-review-list-approval). 상신·반려는 API로 하고 화면은 검토 목록(SCR-06)만 본다.

async function submit(request: Parameters<typeof deviationRun>[0], name: string) {
  const run = await deviationRun(request, name)
  const sent = await request.post(`/api/runs/${run.run_id}/finish-review`,
    { data: { approver_id: APPROVER, comment: COMMENT, actor_id: ENGINEER } })
  expect(sent.status()).toBe(200)
  return run
}

async function find(page: import('@playwright/test').Page, q: string) {
  await page.getByLabel('검색어').fill(q)
  await page.getByLabel('검토 찾기').getByRole('button', { name: '검색' }).click()
}

test('내가 올린 결재 보기', async ({ page, request }) => {
  const tag = `올린 결재 ${Date.now()}`
  await submit(request, `${tag} 대기`)
  const rejected = await submit(request, `${tag} 반려`)
  await request.post(`/api/runs/${rejected.run_id}/approval`,
    { data: { decision: 'REJECTED', comment: '시험 반려', actor_id: APPROVER } })
  await deviationRun(request, `${tag} 상신 전`)          // 상신하지 않은 검토는 보이지 않는다
  await as(page, ENGINEER)
  await page.goto('/#/reviews')
  await page.getByRole('button', { name: '내가 올린 결재' }).click()
  await find(page, tag)
  const rows = page.locator('table.tbl tbody tr')
  await expect(rows).toHaveCount(2)
  const chips = page.getByRole('group', { name: '결재 결정' })
  await expect(chips.getByRole('button', { name: /결재 대기/ })).toContainText('1')
  await expect(chips.getByRole('button', { name: /반려/ })).toContainText('1')
  await expect(rows.nth(0)).toContainText('기본 승인자')
  await expect(rows.nth(1)).toContainText('기본 승인자')
  await expect(page.locator('table.tbl tbody')).toContainText('상신 0일째')
  await expect(page.locator('table.tbl tbody')).toContainText(/반려 \d\d-\d\d \d\d:\d\d/)
  await chips.getByRole('button', { name: /반려/ }).click()
  await expect(rows).toHaveCount(1)
  await expect(rows.first()).toContainText(`${tag} 반려`)
})

test('다른 사람이 올린 결재', async ({ page, request }) => {
  const tag = `남이 올린 결재 ${Date.now()}`
  await submit(request, tag)                        // 기본 엔지니어가 상신
  await as(page, APPROVER)                          // 다른 사용자로 본다
  await page.goto('/#/reviews?scope=submitted')     // 홈 링크와 같은 주소
  await expect(page.getByRole('button', { name: '내가 올린 결재' })).toHaveAttribute('aria-pressed', 'true')
  await find(page, tag)
  await expect(page.locator('table.tbl tbody tr')).toHaveCount(0)
})

// change update-list-summary-filter: 요약 칸 거르기로 넓힘 (단계 칸은 바꾸지 않음)
test('결재 대기 칸으로 거르기', async ({ page, request }) => {
  const tag = `요약 결재 ${Date.now()}`
  await submit(request, `${tag} 1`)
  await submit(request, `${tag} 2`)
  await deviationRun(request, `${tag} 상신 전`)
  await as(page, ENGINEER)
  await page.goto('/#/reviews')
  await page.getByRole('button', { name: '팀 전체' }).click()
  await find(page, tag)                                          // 찾기는 [검색]으로 건다
  await page.locator('.sumline').getByRole('button', { name: /^결재 대기/ }).click()
  const rows = page.locator('table.tbl tbody tr')
  await expect(rows).toHaveCount(2)
  for (const i of [0, 1]) await expect(rows.nth(i)).toContainText('승인 대기')     // 결재 대기 단계의 이름
  await page.locator('.sumbar').getByRole('button', { name: '모두 보기' }).click()
  await expect(rows).toHaveCount(3)
})
