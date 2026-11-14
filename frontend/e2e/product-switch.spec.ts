import { expect, test } from '@playwright/test'
import { ENGINEER, as, openTab } from './helpers'

// 비교 제품 바꿔 보기 (change update-synthetic-product-switch, 명세 reference-data "시연용 합성 RFP").
// 시연용 합성 RFP 파일 28(generate_switch_rfp.py, data/private)을 서버에 둔 RFP에서 골라 처리하고,
// 검토 상세 머리글 "비교 제품"에서 24 kV 차단기 묶음(TS-24-CB)의 제품을 바꿔 판정이 바뀌는 것을 본다.
// 후보 5개(정격 전류 1250·2000·3150 A)라 처음엔 고른 제품이 없고, 요구 정격 전류는 2000 A다.
// 서버에 파일 28이 없으면 건너뛴다. 문서 목록에 28번 줄이 있어야 한다(rfp-db seed-rules).
const FILE_28 = 'RFP_Product_Master_Evaluative_EN_With_Product_Switch'
const LOW = 'VCB-SUSOL-VH-20-40B13'          // 1250 A
const ENOUGH = 'VCB-SUSOL-VH-20-40B20'       // 2000 A

test('비교 제품 바꿔 보기', async ({ page }) => {
  test.setTimeout(300_000)
  await as(page, ENGINEER)
  await page.goto('/#/register')
  const more = page.getByRole('button', { name: '서버에 둔 RFP에서 고르기' })
  await more.waitFor({ timeout: 10_000 }).catch(() => undefined)
  test.skip(!(await more.isVisible()), '서버에 둔 RFP가 없음')
  await more.click()
  const library = page.getByRole('table', { name: '서버에 둔 RFP' })
  const file = (await library.locator('td:nth-child(2)').allTextContents()).find((f) => f.includes(FILE_28))
  test.skip(!file, '서버에 파일 28이 없음 — generate_switch_rfp.py로 만든다')
  await library.getByRole('checkbox', { name: file! }).check()
  await page.getByRole('button', { name: /다음/ }).click()
  await page.getByLabel('제출 마감일').fill('2026-12-31')
  await page.getByRole('button', { name: /다음/ }).click()
  await page.getByRole('button', { name: /등록하고 분석 시작/ }).click()
  const reviewNo = (await page.getByRole('status').filter({ hasText: /RV-\d{4}-\d{3}/ }).textContent())!
    .match(/RV-\d{4}-\d{3}/)![0]
  await page.goto('/#/reviews')
  await page.getByRole('button', { name: '팀 전체' }).click()
  await page.locator('tr', { hasText: reviewNo }).getByRole('link').first().click()
  await expect(page.getByRole('tab', { name: /^판정/ })).toBeVisible({ timeout: 240_000 })

  // 처음: 후보 5개, 코드가 하나로 고르지 못해 눌린 제품이 없다
  const box = page.locator('details.pseg')
  if ((await box.getAttribute('open')) === null) await box.locator('summary').click()   // 묶음이 4개보다 많으면 접혀 있다
  const seg = box.getByRole('group', { name: 'TS-24-CB 비교 제품' })
  await expect(seg.getByRole('button')).toHaveCount(5)
  await expect(seg.locator('button[aria-pressed="true"]')).toHaveCount(0)

  await openTab(page, '판정')
  const row = page.locator('#judge .tw tbody tr', { hasText: 'Rated normal current' })
  await page.getByLabel('판정 검색').fill('Rated normal current')
  await expect(row.first()).toContainText('확인 필요')

  // 1250 A 제품으로 고르면 정격 전류 2000 A 요구는 일탈 후보
  await seg.getByRole('button', { name: LOW }).click()
  await expect(page.getByText('다시 판정 중').first()).toBeHidden({ timeout: 60_000 })
  await expect(seg.getByRole('button', { name: LOW })).toHaveAttribute('aria-pressed', 'true')
  await openTab(page, '판정')
  await page.getByLabel('판정 검색').fill('Rated normal current')
  await expect(row.first()).toContainText('일탈 후보')

  // 2000 A 제품으로 바꾸면 준수
  await seg.getByRole('button', { name: ENOUGH }).click()
  await expect(page.getByText('다시 판정 중').first()).toBeHidden({ timeout: 60_000 })
  await expect(seg.getByRole('button', { name: ENOUGH })).toHaveAttribute('aria-pressed', 'true')
  await openTab(page, '판정')
  await page.getByLabel('판정 검색').fill('Rated normal current')
  await expect(row.first()).toContainText('준수')
  await expect(box).toContainText('엔지니어가 고름 1개')
})
