import { expect, test, type Page } from '@playwright/test'

// 명세 review-workspace "판정 상세 화면"·"판정 상세 근거와 출처"·"판정 상세에서 확정과 바꾸기"의 Scenario (change add-judgment-view).
// 검토 하나의 API 응답을 테스트가 정한 값으로 바꿔 화면만 본다(백엔드·RFP 원문 없이). 원문 줄 API는 백엔드 tests/test_judgment_view.py.

const ID = 9201
type J = Record<string, unknown> & { judgment_id: number; result: string; review_status: string }

function judgment(id: number, result: string, name: string, extra: Record<string, unknown> = {}): J {
  return {
    judgment_id: id, requirement_id: id + 100, equipment_group: '230 kV GIS', result, reason_code: 'R', reason_text: `${name} 비교 규칙`,
    product_code: 'LSG-245-50', product_selected_by: 'AUTO', product_value_raw: '3150', product_value_unit: 'A', margin_value: null, margin_kind: null,
    margin_direction: 'STRENGTH', is_assumed: false, review_status: 'CANDIDATE', req_value_raw: '4000', req_num: 4000, unit_raw: 'A', cond_time_s: null,
    item_key: 'rated_current', item_name: name, item_name_raw: `${name} (en)`, type_code: 'TECH_PERF', type_name: '기술 성능', past_decision: null,
    locations: [{ file_no: 91, section_no: '6.2', section_title: 'Ratings', table_name: null, item_no: null, line_start: 7100, line_end: 7100 }],
    ...extra,
  }
}

async function mock(page: Page, stage = 'ENGINEER_REVIEW', withWarranty = false) {
  const now = new Date().toISOString()
  const list: J[] = [
    judgment(501, 'DEVIATION_CANDIDATE', '주 모선 정격 전류', {
      is_assumed: true,
      locations: [
        { file_no: 91, section_no: '6.2', section_title: 'Ratings', table_name: null, item_no: null, line_start: 7100, line_end: 7100 },
        { file_no: 91, section_no: '6.4', section_title: 'Bus coupler', table_name: null, item_no: null, line_start: 7161, line_end: 7161 },
      ],
    }),
    judgment(502, 'DEVIATION_CANDIDATE', '모선 연결 정격 전류'),
    judgment(503, 'COMPLY', '정격 주파수', { req_value_raw: '50', unit_raw: 'Hz', product_value_raw: '50', product_value_unit: 'Hz', item_key: 'rated_frequency' }),
    ...(withWarranty ? [judgment(504, 'WARRANTY_TO_FILL', '부분 방전', { req_value_raw: 'Bidder to state', unit_raw: 'pC', product_value_raw: null, item_key: 'partial_discharge' })] : []),
  ]
  // 보증값 후보 (update-judge-tab-preview: 판정 상세 보증값 입력). 값이 들어오면 그 값을 돌려준다
  const wc = { candidate_id: 77, judgment_id: 504, requirement_id: 604, equipment_group: '230 kV GIS', item_key: 'partial_discharge', item_name: '부분 방전',
    item_name_raw: null, candidate_value: null as string | null, candidate_unit: 'pC', source_kind: null as string | null, product_code: null, pm_column: null, fixed_key: null,
    status: 'EMPTY_REVIEW', reason_code: null, is_assumed: false, locations: [] }
  const posts: unknown[] = []
  const run = {
    run_id: ID, review_no: 'RV-TEST-JV', review_name: '115·230 kV GIS', project_name: 'Thai Binh 변전소', customer_name: '고객사 가', country: '베트남',
    due_date: null, engineer_id: 1, engineer_name: '시험 엔지니어', business_id: null, business_no: null, stage, dict_version: 'v', llm_model: null,
    step: 'assign', step_detail: null, step_updated_at: now, failed_step: null, error_message: null, cancel_requested_at: null, retries: 0, retryable: false,
    started_at: now, finished_at: now, documents: 1, requirements: 3, risks: 0, judgments: 3, deviation_candidates: 2, output_items: 0, check_violations: 0, proposals: 0,
  }
  const json: Record<string, unknown> = {
    [`/api/runs/${ID}`]: run,
    '/api/users': [{ user_id: 1, user_name: '시험 엔지니어', role: 'ENGINEER' }, { user_id: 2, user_name: '시험 승인자', role: 'APPROVER' }],
    [`/api/runs/${ID}/documents`]: [{ document_id: 1, file_no: 91, file_name: 'synthetic.docx', bundle: 'A', doc_kind: 'TS', language: 'en', standard_system: 'IEC', judge_target: true, readable: true, classify_by: 'RULE', needs_review: false, line_basis: 'DOCX', requirements: 3 }],
    [`/api/runs/${ID}/approval`]: { stage, approval: null, reasons: [], preview: [], review_ratio: { review: 0, total: 3, threshold: 0.2, hand_fill: 0 }, submission_check: null, read_unchecked: 0 },
    [`/api/runs/${ID}/cost-conditions`]: { conditions: [], impacts: [] },
    '/api/rules/compare': [{ compare_rule_id: 1, table_name: null, item_no: null, item_key: 'rated_current', name_ko: '정격 전류', direction: 'GE', time_condition: false, strength_direction: null, own_strength_direction: null, process_note: null, used: 2 }],
    '/api/products/LSG-245-50': { product_code: 'LSG-245-50', product_name: '245 kV GIS', family: 'GIS', source_doc: 'GIS 카탈로그 p.18', comparison_values_assumed: true, comparison_values_source: '팀 합성', used_in: [], proposals: [], field_history: [] },
  }
  await page.route('**/api/**', async (r) => {
    const url = new URL(r.request().url())
    const path = url.pathname
    const req = path.match(/^\/api\/requirements\/(\d+)$/)
    if (req) return r.fulfill({ json: { requirement_id: Number(req[1]), file_no: 91, file_name: 'synthetic.docx', source_kind: 'SENTENCE', req_kind: 'REQUIREMENT', text_raw: 'The rated normal current shall be 4000 A.', extracted_by: 'AI', confidence: 0.82, is_assumed: false, rule_id: null, supplier_mark: null, dedup_of: null, locations: [], types: [], values: [] } })
    const lines = path.match(/^\/api\/runs\/\d+\/documents\/(\d+)\/lines$/)
    if (lines) {
      const from = Number(url.searchParams.get('from')), to = Number(url.searchParams.get('to'))
      const out = Array.from({ length: to - from + 1 }, (_, i) => from + i)
        .map((n) => ({ line_no: n, text: n === 7100 || n === 7161 ? `The rated normal current shall be 4000 A (줄 ${n}).` : `앞뒤 문장 ${n}` }))
      return r.fulfill({ json: { file_no: Number(lines[1]), file_name: 'synthetic.docx', line_from: from, line_to: to, partial: false, lines: out } })
    }
    if (path === `/api/runs/${ID}/judgment-counts`) {
      return r.fulfill({ json: { by_result: { DEVIATION_CANDIDATE: 2, COMPLY: 1 }, total: 3, unconfirmed: 3, unconfirmed_comply: 1, past_seen: 0, past_differs: 0 } })
    }
    if (path === `/api/runs/${ID}/judgments`) {
      const res = url.searchParams.get('result')
      const rows = list.filter((j) => (!res || j.result === res) && (url.searchParams.get('unconfirmed') !== 'true' || j.review_status === 'CANDIDATE'))
      const off = Number(url.searchParams.get('offset') ?? 0), lim = Number(url.searchParams.get('limit') ?? 100)
      return r.fulfill({ json: rows.slice(off, off + lim), headers: { 'X-Total-Count': String(rows.length) } })
    }
    if (path === `/api/runs/${ID}/actions` && r.request().method() === 'POST') {
      const body = r.request().postDataJSON() as { target_id: number; action: string }
      posts.push(body)
      const j = list.find((x) => x.judgment_id === body.target_id)
      if (j && body.action === 'CONFIRM') j.review_status = 'CONFIRMED'
      const w = body as { target?: string; value?: { value?: string } }
      if (w.target === 'warranty_candidate' && w.value?.value) { wc.candidate_value = w.value.value; wc.source_kind = 'ENGINEER' }
      return r.fulfill({ json: { ok: true } })
    }
    if (path === `/api/runs/${ID}/warranty`) return r.fulfill({ json: withWarranty ? [wc] : [], headers: { 'X-Total-Count': withWarranty ? '1' : '0' } })
    if (path in json) return r.fulfill({ json: json[path] })
    return r.fulfill({ json: [] })
  })
  await page.addInitScript(() => localStorage.setItem('s2w.user', '1'))
  return posts
}

const view = (page: Page) => page.getByRole('region', { name: /정격 전류|정격 주파수/ })

test('판정 상세 화면 열기', async ({ page }) => {
  await mock(page)
  await page.goto(`/#/reviews/${ID}`)
  await page.locator('.fbar .chip', { hasText: '일탈 후보' }).click()
  await page.locator('#judge .tw tbody tr').first().click()
  await expect(page).toHaveURL(new RegExp(`#/reviews/${ID}/judgments/501\\?f=DEVIATION_CANDIDATE$`))
  await expect(page.locator('.mdpos')).toHaveText('판정 1 / 2')
  const cmp = page.locator('.cmp')
  await expect(cmp).toContainText('4000 A')
  await expect(cmp).toContainText('3150 A')
  await expect(cmp.locator('.op')).toHaveText('≤')
  await expect(page.locator('.basis')).toContainText('비교 방향정격 전류: 제품값이 같거나 커야 함')
  await expect(page.locator('.jv-ctx')).toContainText('RV-TEST-JV')
})

test('이전·다음과 목록으로', async ({ page }) => {
  await mock(page)
  await page.goto(`/#/reviews/${ID}/judgments/501?f=DEVIATION_CANDIDATE`)
  await expect(page.locator('.mdpos')).toHaveText('판정 1 / 2')
  await expect(page.getByRole('button', { name: '이전 판정' })).toBeDisabled()
  await page.keyboard.press('ArrowDown')
  await expect(page.locator('.mdpos')).toHaveText('판정 2 / 2')
  await expect(page.locator('h1#mdTitle')).toContainText('모선 연결 정격 전류')
  await expect(page.getByRole('button', { name: '다음 판정' })).toBeDisabled()
  await page.keyboard.press('Escape')
  await expect(page).toHaveURL(new RegExp(`#/reviews/${ID}\\?f=DEVIATION_CANDIDATE&cur=502$`))
  await expect(page.locator('.fbar .chip', { hasText: '일탈 후보' })).toHaveAttribute('aria-pressed', 'true')
  await expect(page.locator('#judge tr.cur')).toContainText('모선 연결 정격 전류')
})

test('위치 탭과 원문 앞뒤 줄', async ({ page }) => {
  await mock(page)
  await page.goto(`/#/reviews/${ID}/judgments/501`)
  const tabs = page.getByRole('tab', { name: /본문 \d+행/ })
  await expect(tabs).toHaveCount(2)
  const paper = page.locator('.paper')
  await expect(paper.locator('.pl.hitl .lno')).toHaveText('7100')
  await tabs.nth(1).click()
  await expect(tabs.nth(1)).toHaveAttribute('aria-selected', 'true')
  await expect(paper.locator('.sect')).toContainText('6.4')
  await expect(paper.locator('.pl .lno')).toHaveText(['7159', '7160', '7161', '7162', '7163'])
  await expect(paper.locator('.pl.hitl .lno')).toHaveText('7161')
  await expect(paper.locator('.pl.hitl mark')).toHaveText('4000')
})

test('이 검토에 없는 판정', async ({ page }) => {
  await mock(page)
  await page.goto(`/#/reviews/${ID}/judgments/999`)
  await expect(page.getByText('이 검토에 없는 판정입니다.')).toBeVisible()
  await expect(page.getByRole('link', { name: '판정 목록으로' }).last()).toHaveAttribute('href', `#/reviews/${ID}`)
})

test('팀 가정 표시', async ({ page }) => {
  await mock(page)
  await page.goto(`/#/reviews/${ID}/judgments/501`)
  const src = page.locator('.basis div', { hasText: '제품값 출처' })
  await expect(src).toContainText('LSG-245-50 · 제품표 (GIS 카탈로그 p.18)')
  await expect(src.locator('.st')).toHaveText('팀 가정')
})

test('찾은 방법과 신뢰도', async ({ page }) => {
  await mock(page)
  await page.goto(`/#/reviews/${ID}/judgments/502`)
  const pv = page.locator('.pv')
  await expect(pv).toContainText('찾은 방법AI 추출신뢰도 0.82')
  await expect(pv).toContainText('시스템 제안일탈 후보규칙 기반')
  await expect(pv).toContainText('아직 확정 안 함')
})

test('제안대로 확정하고 다음 판정', async ({ page }) => {
  const posts = await mock(page)
  await page.goto(`/#/reviews/${ID}/judgments/501`)
  await expect(view(page)).toBeVisible()
  await page.getByRole('button', { name: '제안대로 확정' }).click()
  await expect(page.locator('.uisnk')).toContainText('판정을 제안대로 확정했습니다.')
  await expect(page.locator('h1#mdTitle')).toContainText('모선 연결 정격 전류')
  await expect(page.locator('.mdpos')).toHaveText('판정 2 / 3')
  expect(posts).toEqual([expect.objectContaining({ target_id: 501, action: 'CONFIRM', actor_id: 1 })])
})

test('단계 때문에 못 고침', async ({ page }) => {
  await mock(page, 'APPROVAL')
  await page.goto(`/#/reviews/${ID}/judgments/501`)
  for (const name of ['판정 변경', '제안대로 확정']) {
    const b = page.getByRole('button', { name, exact: true })
    await expect(b).toBeDisabled()
    await expect(b).toHaveAttribute('title', '승인 대기 중에는 고칠 수 없습니다')
  }
})

test('사유 필수', async ({ page }) => {
  const posts = await mock(page)
  await page.goto(`/#/reviews/${ID}/judgments/501`)
  await page.getByRole('button', { name: '판정 변경' }).click()
  const dlg = page.getByRole('dialog', { name: '판정 변경' })
  await dlg.getByLabel('새 판정').selectOption('QUERY_CANDIDATE')
  await dlg.getByRole('button', { name: '적용' }).click()
  await expect(dlg.getByRole('alert')).toHaveText('판정을 바꾸려면 사유를 적어 주세요.')
  expect(posts).toEqual([])
  await page.keyboard.press('Escape')
  await expect(dlg).toHaveCount(0)
  await expect(page.locator('.mdh .st')).toHaveText('일탈 후보')
})

// 명세 review-workspace "판정 탭 원문 말풍선"·"판정 상세 보증값 입력" (change update-judge-tab-preview)
test('줄에 마우스를 올려 원문 보기', async ({ page }) => {
  await mock(page)
  await page.goto(`/#/reviews/${ID}`)
  await expect(page.getByRole('complementary', { name: '원문과 판정' })).toHaveCount(0)   // 오른쪽 패널 없음
  const row = page.locator('#judge .tw tbody tr').first()
  await row.hover()
  const tip = page.getByRole('tooltip')
  await expect(tip).toContainText('synthetic.docx')                                   // 원문 위치
  await expect(tip).toContainText('The rated normal current shall be 4000 A.')
  await expect(tip.locator('mark')).toHaveText('4000')
  await page.mouse.move(5, 5)
  await expect(tip).toHaveCount(0)
})

test('키보드로 판정 상세 열기', async ({ page }) => {
  await mock(page)
  await page.goto(`/#/reviews/${ID}`)
  const row = page.locator('#judge .tw tbody tr').first()
  await row.focus()
  await expect(page.getByRole('tooltip')).toBeVisible()
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(new RegExp(`#/reviews/${ID}/judgments/501`))
})

test('판정 상세에서 보증값 넣기', async ({ page }) => {
  const posts = await mock(page, 'ENGINEER_REVIEW', true)
  await page.goto(`/#/reviews/${ID}/judgments/504`)
  await page.getByLabel('보증값', { exact: true }).fill('5')
  await page.getByLabel('보증값 근거').fill('시험 성적서 p.3')
  await page.getByRole('button', { name: '입력' }).click()
  await expect(page.locator('.uisnk')).toContainText('보증값을 입력했습니다')
  expect(posts).toContainEqual(expect.objectContaining({ target: 'warranty_candidate', target_id: 77, action: 'EDIT', value: { value: '5' }, reason: '시험 성적서 p.3' }))
  await expect(page.locator('.jv')).toContainText('5 pC')
})
