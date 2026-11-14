import { expect, test, type Page } from '@playwright/test'

// 명세 review-workspace "판정 상세에서 질의 보냄"·"판정 표 질의 꼬리표"의 Scenario (change add-query-sent).
// 검토 하나의 응답을 테스트가 정한 값으로 바꿔 화면만 본다. 저장·이어받기는 백엔드 tests/test_query_sent.py.

const ID = 9221
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

async function mock(page: Page, stage = 'ENGINEER_REVIEW', userId = 1) {
  const now = new Date().toISOString()
  const list: J[] = [
    judgment(501, 'DEVIATION_CANDIDATE', '주 모선 정격 전류', {
      is_assumed: true,
      locations: [
        { file_no: 91, section_no: '6.2', section_title: 'Ratings', table_name: null, item_no: null, line_start: 7100, line_end: 7100 },
        { file_no: 91, section_no: '6.4', section_title: 'Bus coupler', table_name: null, item_no: null, line_start: 7161, line_end: 7161 },
      ],
    }),
    judgment(502, 'QUERY_CANDIDATE', '모선 연결 정격 전류'),
    judgment(503, 'COMPLY', '정격 주파수', { req_value_raw: '50', unit_raw: 'Hz', product_value_raw: '50', product_value_unit: 'Hz', item_key: 'rated_frequency' }),
  ]
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
      if (j && body.action === 'QUERY_SENT') Object.assign(j, { query_sent_at: new Date().toISOString(), query_sent_by_name: '시험 엔지니어' })
      if (j && body.action === 'QUERY_UNSENT') Object.assign(j, { query_sent_at: null, query_sent_by_name: null })
      return r.fulfill({ json: { ok: true } })
    }
    if (path in json) return r.fulfill({ json: json[path] })
    return r.fulfill({ json: [] })
  })
  await page.addInitScript((id) => localStorage.setItem('s2w.user', String(id)), userId)
  return posts
}

const p2 = (n: number) => String(n).padStart(2, '0')
const today = () => { const d = new Date(); return `${p2(d.getMonth() + 1)}-${p2(d.getDate())}` }

test('질의 보냄 표시', async ({ page }) => {
  const posts = await mock(page)
  await page.goto(`/#/reviews/${ID}/judgments/502`)
  const box = page.locator('.jv-qs')
  await expect(box.locator('.tag')).toHaveText('질의 초안')
  await box.getByRole('button', { name: '질의 보냄 표시' }).click()
  await expect(page.getByText('질의 보냄으로 표시했습니다.')).toBeVisible()
  await expect(box.locator('.tag')).toHaveText(`질의 보냄 · ${today()}`)
  expect(posts).toContainEqual(expect.objectContaining({ target_id: 502, action: 'QUERY_SENT' }))
  // 판정 목록 줄에도 같은 꼬리표
  await page.keyboard.press('Escape')
  await expect(page.locator('#judge .tw tbody tr', { hasText: '모선 연결 정격 전류' })).toContainText(`질의 보냄 · ${today()}`)
})

test('질의 보냄 되돌리기', async ({ page }) => {
  const posts = await mock(page)
  await page.goto(`/#/reviews/${ID}/judgments/502`)
  const box = page.locator('.jv-qs')
  await box.getByRole('button', { name: '질의 보냄 표시' }).click()
  await box.getByRole('button', { name: '되돌리기' }).click()
  await expect(box.locator('.tag')).toHaveText('질의 초안')
  expect(posts).toContainEqual(expect.objectContaining({ target_id: 502, action: 'QUERY_UNSENT' }))
})

// Scenario: 승인자는 잠김
test('승인자는 질의 보냄을 표시할 수 없다', async ({ page }) => {
  await mock(page, 'ENGINEER_REVIEW', 2)
  await page.goto(`/#/reviews/${ID}/judgments/502`)
  const btn = page.locator('.jv-qs').getByRole('button', { name: '질의 보냄 표시' })
  await expect(btn).toBeDisabled()
  await expect(btn).toHaveAttribute('title', '기술 검토 엔지니어만 고칠 수 있습니다')
})

test('질의 후보가 아니면 질의 칸 없음', async ({ page }) => {
  await mock(page)
  await page.goto(`/#/reviews/${ID}/judgments/501`)
  await expect(page.locator('h1#mdTitle')).toContainText('주 모선 정격 전류')
  await expect(page.locator('.jv-qs')).toHaveCount(0)
})
