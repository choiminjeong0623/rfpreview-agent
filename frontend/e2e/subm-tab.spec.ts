import { readFileSync } from 'node:fs'
import { expect, test } from '@playwright/test'
import { APPROVER, as, COMMENT, deviationRun, ENGINEER, openTab, salesMailUnavailable } from './helpers'

// 명세 review-workspace "제출본 탭"의 Scenario (change update-review-screens).

test('승인된 실행의 제출본', async ({ page, request }) => {
  const run = await deviationRun(request, `제출본 ${Date.now()}`)
  const url = `/api/runs/${run.run_id}`
  expect((await request.post(`${url}/finish-review`, { data: { approver_id: APPROVER, comment: COMMENT, actor_id: ENGINEER } })).status()).toBe(200)
  expect((await request.post(`${url}/approval`, { data: { decision: 'APPROVED', comment: '승인', actor_id: APPROVER } })).status()).toBe(200)
  const summary = await (await request.get(url)).json() as { judgments: number }
  await as(page, ENGINEER)
  await page.goto(`/#/reviews/${run.run_id}`)
  await expect(page.getByRole('button', { name: '제출본 v1 확정' })).toBeDisabled()
  await openTab(page, '제출본')
  const row = page.locator('#subm table.subt tbody tr')
  await expect(row).toHaveCount(1)
  await expect(row.locator('td').first()).toHaveText('v1')
  await expect(row).toContainText(`${summary.judgments}건`)
  await expect(row).toContainText(`일탈 ${run.deviations} · 질의`)
  await expect(row).toContainText('기본 승인자')
  await expect(row.locator('.st')).toHaveText('현재 제출본')
})

test('승인 전 제출본 없음', async ({ page, request }) => {
  const run = await deviationRun(request, `제출본 없음 ${Date.now()}`)
  await as(page, ENGINEER)
  await page.goto(`/#/reviews/${run.run_id}`)
  await openTab(page, '제출본')
  await expect(page.locator('#subm .subempty')).toHaveText(/^아직 확정된 제출본이 없습니다/)
  await expect(page.locator('#subm table.subt')).toHaveCount(0)
})

test('인계 패키지 영업에 넘기기', async ({ page, request }) => {
  // change add-submission-package
  const run = await deviationRun(request, `인계 패키지 ${Date.now()}`)
  const url = `/api/runs/${run.run_id}`
  expect((await request.post(`${url}/finish-review`, { data: { approver_id: APPROVER, comment: COMMENT, actor_id: ENGINEER } })).status()).toBe(200)
  expect((await request.post(`${url}/approval`, { data: { decision: 'APPROVED', comment: '승인', actor_id: APPROVER } })).status()).toBe(200)
  await as(page, ENGINEER)
  await page.goto(`/#/reviews/${run.run_id}`)
  await openTab(page, '제출본')
  const box = page.locator('#subm .subpk')
  const dl = page.waitForEvent('download')
  await box.getByRole('button', { name: '인계 패키지 내려받기' }).click()
  // 헤드리스 Chromium은 blob 내려받기의 한글 파일 이름을 "download"로 줄 때가 있어, 이름은 알림으로 확인한다
  expect(readFileSync(await (await dl).path()).subarray(0, 2).toString()).toBe('PK')
  await expect(page.locator('.uisnk')).toContainText(`인계패키지_${run.review_no}.zip 를 내려받았습니다.`)   // 동작 결과 알림 (update-package-progress)
  await box.getByRole('button', { name: '영업에 넘기기' }).click()
  if (await salesMailUnavailable(page, '인계 패키지를 보냈습니다')) return
  await expect(page.locator('#subm').getByRole('status')).toContainText('인계 패키지를 보냈습니다')
  await expect(box).toContainText('에게 보냄')
  await expect(box.getByRole('button', { name: '다시 넘기기' })).toBeVisible()
})

// 명세 review-workspace "인계 패키지 만드는 동안 진행 표시" (change update-package-progress)
test('인계 패키지 만드는 동안 진행 표시', async ({ page, request }) => {
  const run = await deviationRun(request, `패키지 진행 ${Date.now()}`)
  const url = `/api/runs/${run.run_id}`
  expect((await request.post(`${url}/finish-review`, { data: { approver_id: APPROVER, comment: COMMENT, actor_id: ENGINEER } })).status()).toBe(200)
  expect((await request.post(`${url}/approval`, { data: { decision: 'APPROVED', comment: '승인', actor_id: APPROVER } })).status()).toBe(200)
  // 큰 검토처럼 서버가 늦게 답하게 한다 (응답은 실제 zip)
  await page.route(`**/api/runs/${run.run_id}/package`, async (route) => {
    const res = await route.fetch()
    await new Promise((ok) => setTimeout(ok, 2500))
    await route.fulfill({ response: res })
  })
  await as(page, ENGINEER)
  await page.goto(`/#/reviews/${run.run_id}`)
  await openTab(page, '제출본')
  const box = page.locator('#subm')
  const dl = page.waitForEvent('download')
  await box.getByRole('button', { name: '인계 패키지 내려받기' }).click()
  const bar = box.getByRole('progressbar', { name: '인계 패키지 만드는 중' })
  await expect(bar).toBeVisible()
  await expect(box.locator('.pkprog')).toContainText('어림한 진행입니다')
  await expect(box.locator('.pkprog')).toContainText(/Word 만드는 중|엑셀 만드는 중|zip으로 묶는 중/)
  expect(Number(await bar.getAttribute('aria-valuenow'))).toBeLessThanOrEqual(90)
  await dl
  await expect(bar).toHaveCount(0)
  await expect(page.locator('.uisnk')).toContainText('zip 를 내려받았습니다')
  await page.unrouteAll({ behavior: 'ignoreErrors' })
})

// 명세 review-workspace "인계 패키지 미리 보기" (change add-package-preview)
async function approvedRun(request: import('@playwright/test').APIRequestContext, name: string) {
  const run = await deviationRun(request, `${name} ${Date.now()}`)
  const url = `/api/runs/${run.run_id}`
  expect((await request.post(`${url}/finish-review`, { data: { approver_id: APPROVER, comment: COMMENT, actor_id: ENGINEER } })).status()).toBe(200)
  expect((await request.post(`${url}/approval`, { data: { decision: 'APPROVED', comment: '승인', actor_id: APPROVER } })).status()).toBe(200)
  return run
}

test('인계 패키지 미리 보기', async ({ page, request }) => {
  const run = await approvedRun(request, '미리 보기')
  await as(page, ENGINEER)
  await page.goto(`/#/reviews/${run.run_id}`)
  await openTab(page, '제출본')
  await page.locator('#subm .subpk').getByRole('button', { name: '미리 보기' }).click()
  const dlg = page.getByRole('dialog', { name: '영업 인계 패키지' })
  await expect(dlg).toContainText(run.review_no)
  const kpi = dlg.getByRole('list', { name: '인계 패키지 숫자' }).getByRole('listitem')
  await expect(kpi).toHaveCount(6)
  await expect(kpi.locator('span')).toHaveText(['준수', '일탈', '질의', '확인 필요', '팀 가정', '견적 조건'])
  await expect(kpi.nth(1).locator('b')).toHaveText(String(run.deviations))
  await expect(dlg).toContainText('결재: 기본 승인자')
  await expect(dlg).toContainText('금액은 비워 두었습니다')
  await expect(dlg.getByTestId('cover-card').first()).toContainText('준수')
  await expect(dlg.getByRole('button', { name: '인계 패키지 내려받기' })).toBeVisible()
  await dlg.getByRole('button', { name: '닫기', exact: true }).last().click()
  await expect(dlg).toHaveCount(0)
})

test('미리 보기 탭 바꾸기', async ({ page, request }) => {
  const run = await approvedRun(request, '미리 보기 탭')
  const tbe = await (await request.get(`/api/runs/${run.run_id}/tbe?include=all&lang=ko&base=v1`)).json() as { rows: unknown[] }
  await as(page, ENGINEER)
  await page.goto(`/#/reviews/${run.run_id}`)
  await openTab(page, '제출본')
  await page.locator('#subm .subpk').getByRole('button', { name: '미리 보기' }).click()
  const dlg = page.getByRole('dialog', { name: '영업 인계 패키지' })
  const tab = dlg.getByRole('tab', { name: /TBE 준수표/ })
  await expect(tab.locator('.n')).toHaveText(String(tbe.rows.length))
  await tab.click()
  await expect(tab).toHaveAttribute('aria-selected', 'true')
  await expect(dlg.locator('table.pkv-t tbody tr')).toHaveCount(Math.min(10, tbe.rows.length))
})
