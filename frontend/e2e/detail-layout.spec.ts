import { expect, test, type Route } from '@playwright/test'
import { ENGINEER, as, deviationRun } from './helpers'

// 명세 review-workspace "머리글 비교 제품 고르기"·"긴 목록 페이지 번호"의 Scenario (change update-detail-layout).
// 실제 RFP처럼 설비 묶음과 판정 줄이 많은 경우를 응답을 바꿔 만든다.

test('설비 묶음이 많은 비교 제품', async ({ page, request }) => {
  const run = await deviationRun(request, `묶음 많음 ${Date.now()}`)
  const vcb = Array.from({ length: 14 }, (_, i) => `VCB-SUSOL-VL-20-25B${String(i).padStart(2, '0')}`)
  const groups = Array.from({ length: 12 }, (_, i) => ({
    equipment_group: `T${i}|`, label: `파일 9${i % 3} TS-${i}-GIS ${'긴 절 제목 '.repeat(i % 3)}`, family: 'GIS',
    products: [i === 11 ? vcb[0] : 'GIS-245-50'], selected_by: 'AUTO', chosen_product: null,
    candidates: i === 11 ? vcb : ['GIS-245-50'], judgments: 3, deviations: 0, ambiguous: 0,
  }))
  await page.route(/\/api\/runs\/\d+\/equipment$/, (r: Route) => r.fulfill({ json: groups }))
  await as(page, ENGINEER)
  await page.goto(`/#/reviews/${run.run_id}`)
  const box = page.locator('details.pseg')
  await expect(box).toContainText('설비 12개')
  await expect(box).not.toHaveAttribute('open', '')
  await box.locator('summary').click()
  await expect(box.getByRole('group')).toHaveCount(12)
  // 단추가 많아도 화면 폭을 넘지 않고 줄을 바꾼다
  const width = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  expect(width).toBeLessThanOrEqual(0)
  await expect(page.getByRole('group', { name: 'TS-11-GIS 긴 절 제목 긴 절 제목 비교 제품' }).getByRole('button')).toHaveCount(14)
})

test('페이지가 많은 목록', async ({ page, request }) => {
  const run = await deviationRun(request, `페이지 많음 ${Date.now()}`)
  const asked: string[] = []
  await page.route(/\/api\/runs\/\d+\/judgments\?/, async (r: Route) => {
    asked.push(new URL(r.request().url()).searchParams.get('offset') ?? '')
    const res = await r.fetch()
    await r.fulfill({ response: res, headers: { ...res.headers(), 'x-total-count': '1537' } })
  })
  await as(page, ENGINEER)
  await page.goto(`/#/reviews/${run.run_id}`)
  const nav = page.getByRole('navigation', { name: '페이지' })
  await expect(nav.getByRole('button', { name: '154', exact: true })).toBeVisible()
  expect(await nav.getByRole('button').count()).toBeLessThanOrEqual(11)        // 이전·다음 + 번호 9개 이하
  await nav.getByRole('button', { name: '154', exact: true }).click()
  await expect(nav.getByRole('button', { name: '154', exact: true })).toHaveAttribute('aria-current', 'page')
  await expect(nav.getByRole('button', { name: '150', exact: true })).toBeVisible()
  await expect.poll(() => asked.at(-1)).toBe('1530')
  await nav.getByRole('button', { name: '이전 페이지' }).click()
  await expect(nav.getByRole('button', { name: '153', exact: true })).toHaveAttribute('aria-current', 'page')
  await expect(page.locator('.pager select')).toBeVisible()
  await page.unrouteAll({ behavior: 'ignoreErrors' })                          // 끝난 뒤 늦게 온 요청이 닫힌 화면에서 실패하지 않게
})

test('후보가 하나뿐인 비교 제품', async ({ page, request }) => {
  const run = await deviationRun(request, `후보 하나 ${Date.now()}`)
  const groups = [{
    equipment_group: 'T1|', label: '파일 101 TS-145-GIS', family: 'GIS', products: ['GIS-145-40'], selected_by: 'AUTO',
    chosen_product: null, candidates: ['GIS-145-40'], judgments: 14, deviations: 1, ambiguous: 0,
  }]
  await page.route(/\/api\/runs\/\d+\/equipment$/, (r: Route) => r.fulfill({ json: groups }))
  await as(page, ENGINEER)
  await page.goto(`/#/reviews/${run.run_id}`)
  const box = page.locator('details.pseg')
  // 바꿀 제품이 없으면 "펼쳐서 바꾸기" 대신 "펼쳐 보기", 줄 옆에 "다른 후보 없음"
  await expect(box.locator('.pseg-tg')).toHaveText('펼쳐 보기')
  await expect(box.getByRole('group', { name: 'TS-145-GIS 비교 제품' }).getByRole('button')).toHaveCount(1)
  await expect(box.getByText('다른 후보 없음')).toBeVisible()
})

test('다시 판정 중 화면 막기', async ({ page, request }) => {
  // 명세 review-workspace "머리글 비교 제품 고르기" (change update-rejudge-busy)
  const run = await deviationRun(request, `다시 판정 ${Date.now()}`)
  let chosen: string | null = null
  let release: () => void = () => {}
  const held = new Promise<void>((done) => { release = done })
  await page.route(/\/api\/runs\/\d+\/equipment$/, (r: Route) => r.fulfill({ json: [{
    equipment_group: 'T7|', label: '파일 91 TS-245-GIS', family: 'GIS', products: [chosen ?? 'GIS-245-40'], selected_by: chosen ? 'ENGINEER' : 'AUTO',
    chosen_product: chosen, candidates: ['GIS-245-40', 'GIS-245-50'], judgments: 11, deviations: 0, ambiguous: 0,
  }] }))
  await page.route(/\/api\/runs\/\d+\/equipment\/.+\/product$/, async (r: Route) => {
    await held                                       // 다시 판정이 끝나지 않은 상태를 붙잡아 둔다
    chosen = r.request().postDataJSON().product_code
    await r.fulfill({ json: { judgments: 11 } })
  })
  await as(page, ENGINEER)
  await page.goto(`/#/reviews/${run.run_id}`)
  await page.getByRole('group', { name: 'TS-245-GIS 비교 제품' }).getByRole('button', { name: 'GIS-245-50' }).click()
  const cover = page.getByRole('alertdialog', { name: '다시 판정 중…' })
  await expect(cover).toBeVisible()
  await expect(cover).toContainText('TS-245-GIS · GIS-245-50')
  // 막이 클릭을 가로채 탭과 다른 단추가 눌리지 않는다
  await expect(page.getByRole('tab', { name: '위험 조건' }).click({ trial: true, timeout: 1500 })).rejects.toThrow()
  await expect(page.getByRole('button', { name: '결재 상신' }).click({ trial: true, timeout: 1500 })).rejects.toThrow()
  release()
  await expect(cover).toBeHidden()
  await expect(page.getByRole('group', { name: 'TS-245-GIS 비교 제품' }).getByRole('button', { name: 'GIS-245-50' }))
    .toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByRole('tab', { name: '판정' })).toHaveAttribute('aria-selected', 'true')
})
