import { expect, test, type Page } from '@playwright/test'

// 명세 review-workspace "제품 상세 화면"·"요구 조건으로 찾기"·"제품표 화면"(빠른 보기·대신 쓸 수 있는 제품)의 Scenario
// (change add-product-view). 제품표 API 응답을 테스트가 정한 값으로 바꿔 화면만 본다. 백엔드 칸은 tests/test_reference_views.py.

function product(code: string, kv: number, a: number, ka: number, extra: Record<string, unknown> = {}) {
  return {
    product_code: code, product_name: `${kv} kV GIS`, family: 'GIS', rated_voltage_kv: kv, rated_current_a: a, short_circuit_ka: ka, rated_frequency: '50/60',
    rated_capacity: null, rated_capacity_unit: null, weight_kg: 5200, noload_loss_kw: null, load_loss_kw: null, aux_loss_kw: null, loss_is_assumed: false,
    lightning_impulse_kv: 650, power_freq_withstand_kv: 275, switching_impulse_kv: null, peak_current_ka: ka * 2.5, making_current_ka: null,
    breaking_time_ms: 60, closing_time_ms: null, gas_leakage_percent: 0.5, partial_discharge_pc: null, cooling_type: null, insulation_medium: 'SF6',
    maintenance_months: null, service_life_years: null, warranty_months: null, comparison_values_assumed: false, comparison_values_source: null,
    is_assumed: false, is_design_card: false, source_doc: 'CAT-C30101-12 p.18', lifecycle_status: 'ACTIVE', used: 0,
    value_columns: ['rated_voltage_kv', 'rated_current_a', 'short_circuit_ka', 'peak_current_ka', 'gas_leakage_percent', 'partial_discharge_pc'],
    empty_columns: [], empty_count: 0, ...extra,
  }
}

const A = product('GIS-145-40', 145, 3150, 40, {
  comparison_values_assumed: true, comparison_values_source: '팀 합성', partial_discharge_pc: null,
  // 팀 가정 비교값은 뇌 임펄스·상용 주파 2칸만 값이 있다
  peak_current_ka: null, breaking_time_ms: null, gas_leakage_percent: null, insulation_medium: null, empty_columns: ['partial_discharge_pc'], empty_count: 1, used: 3,
})
const B = product('GIS-145-50', 145, 4000, 50)
const C = product('GIS-170-40', 170, 3150, 40, { partial_discharge_pc: 5 })
const DETAIL = {
  ...A, used_runs: 2, proposals: [{ point_id: 1, run_id: 71, point_kind: 'MARGIN', status: 'CANDIDATE', text_draft: '여유', is_assumed: false }],
  used_in: [
    { run_id: 72, review_no: 'RV-2026-072', project_name: 'Thai Binh', review_name: '145 kV GIS', judgment_id: 901, equipment_group: '145 kV GIS', item_name: '부분 방전',
      result: 'NEEDS_REVIEW', product_selected_by: 'AUTO', item_key: 'partial_discharge', due_date: '2026-12-31' },
    { run_id: 72, review_no: 'RV-2026-072', project_name: 'Thai Binh', review_name: '145 kV GIS', judgment_id: 902, equipment_group: '145 kV GIS', item_name: '정격 전류',
      result: 'COMPLY', product_selected_by: 'AUTO', item_key: 'rated_current', due_date: '2026-12-31' },
    { run_id: 71, review_no: 'RV-2026-071', project_name: 'Song Hau', review_name: '변전소 1차', judgment_id: 903, equipment_group: '145 kV GIS', item_name: '단시간 견딤 전류',
      result: 'DEVIATION_CANDIDATE', product_selected_by: 'AUTO', item_key: 'short_time_current', due_date: null },
  ],
  field_history: [],
}
const ITEMS = [
  { item_key: 'rated_voltage_um', name_ko: '정격 전압', default_direction: 'GE', strength_direction: 'HIGHER', note: null, pm_column: 'rated_voltage_kv', fixed_key: true, aliases: [], used: 0 },
  { item_key: 'rated_current', name_ko: '정격 전류', default_direction: 'GE', strength_direction: 'HIGHER', note: null, pm_column: 'rated_current_a', fixed_key: true, aliases: [], used: 0 },
  { item_key: 'short_time_current', name_ko: '단시간 견딤 전류', default_direction: 'GE', strength_direction: 'HIGHER', note: null, pm_column: 'short_circuit_ka', fixed_key: true, aliases: [], used: 0 },
  { item_key: 'partial_discharge', name_ko: '부분 방전', default_direction: 'LE', strength_direction: 'LOWER', note: null, pm_column: 'partial_discharge_pc', fixed_key: true, aliases: [], used: 0 },
]
const RUNS = [
  { run_id: 72, review_no: 'RV-2026-072', review_name: '145 kV GIS', project_name: 'Thai Binh', customer_name: '고객사 가', stage: 'ENGINEER_REVIEW', due_date: '2026-12-31', engineer_id: 1 },
  { run_id: 71, review_no: 'RV-2026-071', review_name: '변전소 1차', project_name: 'Song Hau', customer_name: '고객사 나', stage: 'APPROVED', due_date: null, engineer_id: 2 },
]
const req = (item_key: string, n: number) => ({ judgment_id: n, item_key, req_num: n, req_value_raw: String(n) })

async function mock(page: Page) {
  const list = [A, B, C]
  await page.route('**/api/**', async (r) => {
    const url = new URL(r.request().url())
    const path = url.pathname
    if (path === '/api/products') {
      const q = (url.searchParams.get('q') ?? '').toLowerCase()
      const rows = list.filter((p) => !q || p.product_code.toLowerCase().includes(q))
      return r.fulfill({ json: rows, headers: { 'X-Total-Count': String(rows.length) } })
    }
    if (path === '/api/products/families') return r.fulfill({ json: [{ family: 'GIS', products: 3, empty_cells: 1, with_empty: 1, assumed: 1, design_cards: 0 }] })
    if (path === '/api/products/GIS-145-40') return r.fulfill({ json: DETAIL })
    if (path.startsWith('/api/products/')) {
      const code = decodeURIComponent(path.split('/').pop()!)
      const p = list.find((x) => x.product_code === code)
      return p ? r.fulfill({ json: { ...p, used_runs: 0, used_in: [], proposals: [], field_history: [] } })
        : r.fulfill({ status: 404, json: { detail: `제품 ${code}이(가) 제품표에 없습니다.` } })
    }
    if (path === '/api/rules/items') return r.fulfill({ json: ITEMS })
    if (path === '/api/runs') return r.fulfill({ json: RUNS })
    if (path === '/api/runs/72/judgments') return r.fulfill({ json: [req('rated_voltage_um', 145), req('rated_current', 4000), req('short_time_current', 40)] })
    if (path === '/api/runs/71/judgments') return r.fulfill({ json: [] })
    if (path === '/api/users') return r.fulfill({ json: [{ user_id: 1, user_name: '시험 엔지니어', role: 'ENGINEER' }] })
    return r.fulfill({ json: [] })
  })
  await page.addInitScript(() => localStorage.setItem('s2w.user', '1'))
}

const quick = (page: Page) => page.getByRole('complementary', { name: '제품 빠른 보기' })

test('빠른 보기와 상세 화면', async ({ page }) => {
  await mock(page)
  await page.goto('/#/products')
  await page.locator('tbody tr', { hasText: 'GIS-145-40' }).locator('td').nth(2).click()
  const qv = quick(page)
  await expect(qv.locator('.qv-t')).toContainText('정격 전압')
  await expect(qv.locator('.qv-t')).toContainText('145')
  await expect(qv.locator('.qv-u').first()).toContainText('RV-2026-072')
  await expect(qv.locator('.qv-u').first()).toContainText('준수 1 · 일탈 0 · 확인 필요 1')
  await expect(qv.locator('.qv-u').first()).toHaveAttribute('href', '#/reviews/72')
  await qv.getByRole('link', { name: '상세 화면' }).click()
  await expect(page).toHaveURL(/#\/products\/GIS-145-40$/)
})

test('대신 쓸 수 있는 제품', async ({ page }) => {
  await mock(page)
  await page.goto('/#/products?code=GIS-145-40')
  const alt = quick(page).locator('.qv-a')
  await expect(alt).toHaveCount(2)
  await expect(alt.first()).toContainText('GIS-145-50')
  await expect(alt.first()).toContainText('단시간 50 kA (+10)')
  await expect(alt.nth(1)).toContainText('GIS-170-40')
  await expect(alt.nth(1)).toContainText('부분 방전 값 있음')
  await expect(quick(page).locator('.qv-blk')).toContainText('값이 없어 막힌 판정 1')
})

test('제품 상세 화면 열기', async ({ page }) => {
  await mock(page)
  await page.goto('/#/products')
  await page.getByRole('link', { name: 'GIS-145-50' }).click()
  await expect(page).toHaveURL(/#\/products\/GIS-145-50$/)
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('GIS-145-50')
  const row = page.locator('.pinfo tbody tr', { hasText: '정격 전압' })
  await expect(row).toContainText('145')
  await expect(row).toContainText('클수록 강점')
})

test('쓰인 곳', async ({ page }) => {
  await mock(page)
  await page.goto('/#/products/GIS-145-40')
  await page.getByRole('tab', { name: '쓰인 곳' }).click()
  const u = page.locator('.pinfo .qv-u', { hasText: 'RV-2026-072' })
  await expect(u).toContainText('판정 2')
  await u.click()
  await expect(page).toHaveURL(/#\/reviews\/72$/)
})

test('팀 가정 표시', async ({ page }) => {
  await mock(page)
  await page.goto('/#/products/GIS-145-40')
  await expect(page.getByRole('region', { name: '근거 상태' })).toContainText('팀 가정2')
  await expect(page.locator('.pinfo tbody tr', { hasText: '뇌 임펄스 내전압' })).toContainText('팀 가정')
  await expect(page.locator('.pinfo tbody tr', { hasText: '정격 전압' })).not.toContainText('팀 가정')
})

test('막힌 판정', async ({ page }) => {
  await mock(page)
  await page.goto('/#/products/GIS-145-40')
  const use = page.getByRole('region', { name: '쓰임' })
  await expect(use).toContainText('값이 없어 막힌 판정1')
  await expect(use.locator('.qv-b')).toContainText('부분 방전')
})

test('없는 제품', async ({ page }) => {
  await mock(page)
  await page.goto('/#/products/NO-SUCH')
  await expect(page.getByText('제품표에 없는 제품입니다 (NO-SUCH)')).toBeVisible()
  await page.locator('.ttl').getByRole('link', { name: '제품표' }).click()
  await expect(page).toHaveURL(/#\/products\?code=NO-SUCH$/)
})

test('요구 조건으로 거르기', async ({ page }) => {
  await mock(page)
  await page.goto('/#/products')
  await page.getByRole('button', { name: '요구 조건으로 찾기' }).click()
  await page.getByLabel('정격 전류 이상 (A)').fill('4000')
  const rows = page.locator('.work .tw tbody tr')
  await expect(rows).toHaveCount(1)
  await expect(rows.first()).toContainText('GIS-145-50')
  await expect(rows.first().locator('.fit')).toHaveText('모두 맞음')
  await expect(page.locator('.rqsum')).toHaveText('모두 맞음 1 · 모자람 2 · 값 없음 0')
})

test('RFP 검토 찾기', async ({ page }) => {
  await mock(page)
  await page.goto('/#/products')
  await page.getByRole('button', { name: '요구 조건으로 찾기' }).click()
  await page.getByRole('button', { name: 'RFP 검토 찾기' }).click()
  const dlg = page.getByRole('dialog', { name: 'RFP 검토 찾기' })
  await expect(dlg.locator('tbody tr', { hasText: 'RV-2026-072' })).toContainText('145 kV · 4000 A · 40 kA')
  await dlg.getByLabel('RV-2026-072 고르기').check()
  await dlg.getByRole('button', { name: '요구값 넣기' }).click()
  await expect(dlg).toBeHidden()
  await expect(page.getByLabel('정격 전압 (kV)')).toHaveValue('145')
  await expect(page.getByLabel('정격 전류 이상 (A)')).toHaveValue('4000')
  await expect(page.getByLabel('단시간 견딤 이상 (kA)')).toHaveValue('40')
  await expect(page.locator('.rqt small')).toHaveText('RV-2026-072 요구사항에서 가져옴')
  await expect(page.locator('.work .tw tbody tr')).toHaveCount(1)
})
