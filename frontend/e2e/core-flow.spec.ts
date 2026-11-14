import { readFileSync } from 'node:fs'
import { expect, test } from '@playwright/test'
import { APPROVER, ENGINEER, as, openTab } from './helpers'
import { fileURLToPath } from 'node:url'

// 핵심 흐름 (change add-spec-trace, 명세 spec-verification "핵심 흐름 e2e").
// 엔지니어가 검토 등록 화면에서 RFP를 올리고(FR-01) → 분석이 끝나면 판정 하나를 확정하고(FR-07·FR-10)
// → 결재 상신 → 지정 결재자가 승인 → 제출본 탭에서 인계 패키지(일탈·질의 초안, FR-09)를 내려받는다.
// API로 건너뛰지 않고 화면만 누른다. 합성 데이터시트(fixtures/synthetic_judgment.docx, 고객 원문 아님)는
// 문서 목록에 묶음 A로 있어야 판정이 생긴다(helpers.ts 맨 위 안내).
const DOCX = new URL('./fixtures/synthetic_judgment.docx', import.meta.url)

const isoAfter = (days: number) => new Date(Date.now() + days * 86_400_000).toISOString().slice(0, 10)

test('RFP 한 건 처음부터 끝까지', async ({ page, request }) => {
  test.setTimeout(180_000)
  const name = `핵심 흐름 ${Date.now()}`

  // 1. 검토 등록 (SCR-07): 올리고, 분류 추천을 보고, 검토 정보를 적고 시작
  await as(page, ENGINEER)
  await page.goto('/#/register')
  await page.getByLabel('파일 올리기').setInputFiles(fileURLToPath(DOCX))
  const doc = page.locator('tr', { hasText: 'synthetic_judgment.docx' })
  await expect(doc).toBeVisible()
  test.skip(await page.getByText(/판정 대상.*없/).first().isVisible(), '합성 데이터시트가 문서 목록(묶음 A)에 없습니다')
  await page.getByRole('button', { name: /다음/ }).click()
  await page.getByLabel('설비 범위', { exact: true }).fill(name)
  await page.getByLabel('새 사업명').fill('핵심 흐름 사업')
  await page.getByLabel('제출 마감일').fill(isoAfter(14))
  await page.getByRole('button', { name: /다음/ }).click()
  await page.getByRole('button', { name: /등록하고 분석 시작/ }).click()
  const reviewNo = (await page.getByRole('status').filter({ hasText: /RV-\d{4}-\d{3}/ }).textContent())!
    .match(/RV-\d{4}-\d{3}/)![0]

  // 2. 검토 목록 (SCR-06)에서 그 검토를 열고 분석이 끝나기를 기다린다 (SCR-02 처리 상태 → 담당자 확인)
  await page.goto('/#/reviews')
  await page.locator('tr', { hasText: reviewNo }).getByRole('link').first().click()
  await expect(page).toHaveURL(/#\/reviews\/\d+/)
  const runId = Number(page.url().match(/#\/reviews\/(\d+)/)![1])
  await expect(page.getByRole('tab', { name: /^판정/ })).toBeVisible({ timeout: 120_000 })

  // 3. 판정 탭 (SCR-08-1) → 첫 줄을 눌러 판정 상세 (SCR-08-12) → 제안대로 확정
  await openTab(page, '판정')
  await page.locator('#judge table tbody tr').first().click()
  await expect(page.locator('.jv .mdpos')).toBeVisible()
  await page.getByRole('button', { name: '제안대로 확정' }).click()
  await expect(page.locator('.uisnk')).toContainText('판정을 제안대로 확정했습니다.')
  await page.keyboard.press('Escape')
  await expect(page.locator('#judge')).toBeVisible()

  // 4. 결재 상신 창 (SCR-08-10): 결재자·의견을 넣고 상신
  await page.getByRole('button', { name: '결재 상신' }).click()
  const dialog = page.getByRole('dialog', { name: '결재 상신' })
  await dialog.getByLabel('결재자').selectOption(String(APPROVER))
  await dialog.getByLabel('상신 의견').fill('핵심 흐름 시험: 판정 확인을 마쳤습니다')
  await dialog.getByRole('button', { name: '결재 상신' }).click()
  await expect(page.getByText('기본 승인자의 결재를 기다리고 있습니다')).toBeVisible()

  // 5. 지정 결재자가 결재 대기 화면 (SCR-12)에서 승인
  await page.evaluate((id) => localStorage.setItem('s2w.user', String(id)), APPROVER)
  await page.addInitScript((id) => localStorage.setItem('s2w.user', String(id)), APPROVER)
  await page.goto(`/#/reviews/${runId}`)
  await page.reload()
  await expect(page.getByText('결재할 검토입니다')).toBeVisible()
  await page.getByLabel('결재 의견').fill('승인합니다')
  await page.getByRole('button', { name: '승인', exact: true }).click()
  await expect(page.getByText('승인됨', { exact: true }).first()).toBeVisible()

  // 6. 엔지니어가 제출본 탭 (SCR-08-8)에서 인계 패키지(zip)를 내려받는다
  await page.addInitScript((id) => localStorage.setItem('s2w.user', String(id)), ENGINEER)
  await page.goto(`/#/reviews/${runId}`)
  await page.reload()
  await openTab(page, '제출본')
  const dl = page.waitForEvent('download')
  await page.locator('#subm .subpk').getByRole('button', { name: '인계 패키지 내려받기' }).click()
  expect(readFileSync(await (await dl).path()).subarray(0, 2).toString()).toBe('PK')
  await expect(page.locator('.uisnk')).toContainText(`인계패키지_${reviewNo}.zip 를 내려받았습니다.`)


  // 이력 (SCR-08-9)에 판정 확정이 남는다
  const log = await (await request.get(`/api/runs/${runId}/history`)).json() as { action: string }[]
  expect(log.map((x) => x.action)).toContain('CONFIRM')
})
