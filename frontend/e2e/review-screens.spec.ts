import { expect, test } from '@playwright/test'
import { as, deviationRun, ENGINEER, openTab, backFromJudgment } from './helpers'

// 명세 review-workspace "검토 상세 요약 칸과 탭"·"판정 표 거르기"·"판정 상세 패널"의 Scenario (change update-review-screens).

test('탭으로 내용 바꾸기', async ({ page, request }) => {
  const run = await deviationRun(request, `탭 ${Date.now()}`)
  await page.goto(`/#/reviews/${run.run_id}`)
  const tabs = page.getByRole('tablist', { name: '검토 메뉴' })
  // 탭 5개 + 더 보기 (update-detail-header). 탭 이름 옆 수는 빼고 본다
  await expect(tabs.getByRole('tab')).toHaveText([/^판정/, /^위험 조건/, /^문서 읽기 점검/, /^상업 조건/, '이력'])
  await tabs.getByRole('tab', { name: '이력' }).click()
  await expect(tabs.getByRole('tab', { name: '이력' })).toHaveAttribute('aria-selected', 'true')
  await expect(page.locator('#log')).toContainText('사유: 시험용 일탈')
})

test('예시 탭', async ({ page, request }) => {
  // 마지막 예시 탭이던 지난 RFP 비교도 실제 데이터가 되어(add-past-compare) 예시 띠가 없다
  const run = await deviationRun(request, `예시 탭 ${Date.now()}`)
  await page.goto(`/#/reviews/${run.run_id}`)
  await openTab(page, '지난 RFP 비교')
  await expect(page.locator('#cmp h2')).toContainText('지난 RFP 비교')
  await expect(page.locator('#cmp').getByRole('note')).toHaveCount(0)
})

test('판정 칩으로 거르기', async ({ page, request }) => {
  const run = await deviationRun(request, `칩 ${Date.now()}`)
  await page.goto(`/#/reviews/${run.run_id}`)
  const chip = page.locator('.fbar .chip', { hasText: '질의 후보' })
  const n = Number(await chip.locator('.n').textContent())
  await chip.click()
  await expect(chip).toHaveAttribute('aria-pressed', 'true')
  const rows = page.locator('#judge .tw tbody tr')
  await expect(rows).toHaveCount(n)
  await expect(rows.locator('td:nth-child(2) .st')).toHaveText(Array(n).fill('질의 후보'))
  await expect(page.locator('.tfoot')).toContainText(`${n}건 표시`)
})

test('거른 결과가 없음', async ({ page, request }) => {
  const run = await deviationRun(request, `없음 ${Date.now()}`)
  await page.goto(`/#/reviews/${run.run_id}`)
  await page.getByPlaceholder('항목명, 영문, 원문 문장').fill('없는검색어zz')
  await expect(page.getByText('조건에 맞는 판정이 없습니다.')).toBeVisible()
  await page.getByRole('button', { name: '필터 지우기' }).click()
  await expect(page.locator('#judge .tw tbody tr').first()).toBeVisible()
})

test('줄을 눌러 원문 보기', async ({ page, request }) => {
  const run = await deviationRun(request, `원문 ${Date.now()}`)
  // 확정하지 않은 일탈 후보를 하나 더 만든다 (시험용 일탈은 엔지니어가 바꾼 것)
  const [j] = await (await request.get(`/api/runs/${run.run_id}/judgments?result=QUERY_CANDIDATE&limit=1`)).json()
  await page.goto(`/#/reviews/${run.run_id}`)
  await page.locator('.fbar .chip', { hasText: '질의 후보' }).click()
  await page.locator('#judge .tw tbody tr').first().click()
  const dialog = page.locator('.jv')                                                // 판정 상세 화면 (add-judgment-view)
  await expect(page).toHaveURL(/\/judgments\/\d+\?f=QUERY_CANDIDATE$/)
  await expect(dialog.locator('.mdpos')).toContainText('판정 1 /')
  await expect(dialog.locator('.paper')).toContainText(j.req_value_raw)            // 원문 문장
  await expect(dialog.locator('.basis')).toContainText(j.reason_text)               // 판정 근거
  await expect(dialog.locator('.pv')).toContainText('시스템 제안질의 후보')
  await expect(dialog.locator('.pv')).toContainText('아직 확정 안 함')
  await page.keyboard.press('Escape')
  await expect(page.getByRole('complementary', { name: '원문과 판정' })).toHaveCount(0)   // 오른쪽 패널 없음 (update-judge-tab-preview)
  await expect(page.locator('#judge tr.cur')).toHaveCount(1)                        // 보던 줄 강조
})

test('사유 없이 판정 바꾸기', async ({ page, request }) => {
  const run = await deviationRun(request, `바꾸기 ${Date.now()}`)
  await as(page, ENGINEER)
  await page.goto(`/#/reviews/${run.run_id}`)
  await page.locator('.fbar .chip', { hasText: '확인 필요' }).click()
  const first = page.locator('#judge .tw tbody tr').first()
  await first.click()
  await page.locator('.jv').getByRole('button', { name: '판정 변경' }).click()       // 판정 상세 화면의 판정 변경 창
  const panel = page.getByRole('dialog', { name: '판정 변경' })
  await panel.getByLabel('새 판정').selectOption('QUERY_CANDIDATE')
  const apply = panel.getByRole('button', { name: '적용' })
  await panel.getByLabel('바꾸는 사유').fill('발주처에 확인할 값')
  await apply.click()
  await expect(panel).toHaveCount(0)
  await backFromJudgment(page)
  await page.locator('.fbar .chip', { hasText: '질의 후보' }).click()
  await expect(page.locator('#judge .tw tbody tr', { hasText: '바꿈' }).first()).toBeVisible()
  await page.locator('#judge .tw tbody tr', { hasText: '바꿈' }).first().click()
  await expect(page.locator('.jv .pv')).toContainText('기본 엔지니어')    // 담당자 확정이 바뀜 (판정 상세 화면)
})
