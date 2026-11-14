import { expect, test } from '@playwright/test'
import { as, deviationRun, ENGINEER, exportItem, salesMailUnavailable } from './helpers'

// 명세 review-workspace "데이터시트 채우기 화면"의 Scenario (change add-datasheet-export).

test('칸 확정', async ({ page, request }) => {
  const run = await deviationRun(request, `데이터시트 ${Date.now()}`)
  await as(page, ENGINEER)
  await page.goto(`/#/reviews/${run.run_id}`)
  await exportItem(page, '데이터시트 채우기')
  await expect(page).toHaveURL(new RegExp(`#/reviews/${run.run_id}/datasheet$`))
  const ok = page.getByLabel('요약').locator('div', { hasText: '채움 · 확정' }).locator('b')
  await expect(page.locator('table.ds-t tbody tr').first()).toBeVisible()
  const before = Number(await ok.textContent())
  const row = page.locator('table.ds-t tbody tr', { has: page.getByRole('button', { name: '확정' }) }).first()
  const no = (await row.locator('td').first().textContent())!.trim()
  await row.getByRole('button', { name: '확정' }).click()
  await expect(page.getByRole('status')).toContainText(`칸 ${no} `)
  await expect(page.getByRole('status')).toContainText('값을 확정했습니다.')
  await expect(ok).toHaveText(String(before + 1))
})

test('확인 필요만 보기', async ({ page, request }) => {
  const run = await deviationRun(request, `데이터시트 빈칸 ${Date.now()}`)
  await page.goto(`/#/reviews/${run.run_id}/datasheet`)
  await expect(page.locator('table.ds-t tbody tr').first()).toBeVisible()
  await page.getByRole('radio', { name: '확인 필요' }).check()
  const rows = page.locator('table.ds-t tbody tr')
  await expect(rows.first()).toBeVisible()
  for (const t of await rows.allInnerTexts()) expect(t).toContain('비움')
  await expect(rows.locator('.st')).toHaveText(Array(await rows.count()).fill('확인 필요'))
})

// 영업에 넘기기 (change add-submission-package)

test('후보가 남아 넘기기 막힘', async ({ page, request }) => {
  const run = await deviationRun(request, `데이터시트 넘기기 막힘 ${Date.now()}`)
  await as(page, ENGINEER)
  await page.goto(`/#/reviews/${run.run_id}/datasheet`)
  await expect(page.locator('table.ds-t tbody tr').first()).toBeVisible()
  await expect(page.getByRole('button', { name: '영업에 넘기기' })).toBeDisabled()
  await expect(page.locator('.ds-sent')).toContainText(/후보 \d+칸을 먼저 확정해야 영업에 넘길 수 있습니다/)
})

test('데이터시트 영업에 넘기기', async ({ page, request }) => {
  const run = await deviationRun(request, `데이터시트 넘기기 ${Date.now()}`)
  // 화면은 빈칸이 가장 많은 표를 먼저 연다
  const sheets = await (await request.get(`/api/runs/${run.run_id}/datasheets`)).json() as { table_id: number; empty: number }[]
  const sheet = [...sheets].sort((a, b) => b.empty - a.empty)[0]
  type Row = { state: string; target: string; judgment_id: number; candidate_id: number | null }
  // 화면의 "확정"과 같은 요청. 확정하면 목록을 다시 만들어 줄 번호가 바뀌므로 한 줄씩 다시 읽는다
  for (let i = 0; i < 100; i += 1) {
    const data = await (await request.get(`/api/runs/${run.run_id}/datasheet?table_id=${sheet.table_id}`)).json() as { rows: Row[] }
    const r = data.rows.find((x) => x.state === 'cand')
    if (!r) break
    const body = r.target === 'warranty'
      ? { target: 'warranty_candidate', target_id: r.candidate_id, action: 'CONFIRM', actor_id: ENGINEER }
      : { target: 'judgment', target_id: r.judgment_id, action: 'CONFIRM', actor_id: ENGINEER }
    expect((await request.post(`/api/runs/${run.run_id}/actions`, { data: body })).status()).toBe(200)
  }
  await as(page, ENGINEER)
  await page.goto(`/#/reviews/${run.run_id}/datasheet`)
  await expect(page.locator('table.ds-t tbody tr').first()).toBeVisible()
  await page.getByRole('button', { name: '영업에 넘기기' }).click()
  if (await salesMailUnavailable(page, '영업 담당(')) return
  await expect(page.getByRole('status')).toContainText('영업 담당(')
  await expect(page.getByRole('status')).toContainText('비운 채로 넘어갑니다.')
  await expect(page.getByRole('button', { name: '다시 넘기기' })).toBeEnabled()
  await expect(page.locator('.ds-sent')).toContainText('에게 넘김')
})
