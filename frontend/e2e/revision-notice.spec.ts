import { expect, test, type Page } from '@playwright/test'

// 명세 review-workspace "개정 안내 띠"의 Scenario (change add-revision-notice). 검토 하나의 응답을 테스트가 정한 값으로 바꿔 화면만 본다.
// 개정 결과 계산은 백엔드 tests/test_revision_notice.py.

const ID = 9211
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

async function mock(page: Page, stage = 'ENGINEER_REVIEW', revised = true) {
  const now = new Date().toISOString()
  const list: J[] = [
    judgment(501, 'DEVIATION_CANDIDATE', '주 모선 정격 전류', {
      is_assumed: true, revised: 'CHANGED',
      locations: [
        { file_no: 91, section_no: '6.2', section_title: 'Ratings', table_name: null, item_no: null, line_start: 7100, line_end: 7100 },
        { file_no: 91, section_no: '6.4', section_title: 'Bus coupler', table_name: null, item_no: null, line_start: 7161, line_end: 7161 },
      ],
    }),
    judgment(502, 'DEVIATION_CANDIDATE', '모선 연결 정격 전류', { revised: 'CHANGED' }),
    judgment(504, 'QUERY_CANDIDATE', '정격 단시간 견딤 전류', { revised: 'ADDED', item_key: 'short_time_current' }),
    judgment(503, 'COMPLY', '정격 주파수', { req_value_raw: '50', unit_raw: 'Hz', product_value_raw: '50', product_value_unit: 'Hz', item_key: 'rated_frequency' }),
  ]
  const posts: unknown[] = []
  const run = {
    run_id: ID, review_no: 'RV-TEST-JV', review_name: '115·230 kV GIS', project_name: 'Thai Binh 변전소', customer_name: '고객사 가', country: '베트남',
    due_date: null, engineer_id: 1, engineer_name: '시험 엔지니어', business_id: null, business_no: null, stage, dict_version: 'v', llm_model: null,
    step: 'assign', step_detail: null, step_updated_at: now, failed_step: null, error_message: null, cancel_requested_at: null, retries: 0, retryable: false,
    started_at: now, finished_at: now, documents: 1, requirements: 3, risks: 0, judgments: 3, deviation_candidates: 2, output_items: 0, check_violations: 0, proposals: 0,
    revision: { no: 1, at: now, files: ['Addendum_No1.docx'], changed: 2, added: 1, removed: 1 },
  }
  const json: Record<string, unknown> = {
    [`/api/runs/${ID}`]: revised ? run : { ...run, revision: null },
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
      const rows = list.filter((j) => (!res || j.result === res) && (url.searchParams.get('unconfirmed') !== 'true' || j.review_status === 'CANDIDATE')
        && (url.searchParams.get('revised') !== 'true' || j.revised))
      const off = Number(url.searchParams.get('offset') ?? 0), lim = Number(url.searchParams.get('limit') ?? 100)
      return r.fulfill({ json: rows.slice(off, off + lim), headers: { 'X-Total-Count': String(rows.length) } })
    }
    if (path === `/api/runs/${ID}/actions` && r.request().method() === 'POST') {
      const body = r.request().postDataJSON() as { target_id: number; action: string }
      posts.push(body)
      const j = list.find((x) => x.judgment_id === body.target_id)
      if (j && body.action === 'CONFIRM') j.review_status = 'CONFIRMED'
      return r.fulfill({ json: { ok: true } })
    }
    if (path in json) return r.fulfill({ json: json[path] })
    return r.fulfill({ json: [] })
  })
  await page.addInitScript(() => localStorage.setItem('s2w.user', '1'))
  return posts
}

const bar = (page: Page) => page.getByRole('status', { name: '개정 안내' })
const rows = (page: Page) => page.locator('#judge .tw tbody tr')

test('개정 안내 띠', async ({ page }) => {
  await mock(page)
  await page.goto(`/#/reviews/${ID}`)
  await expect(bar(page)).toContainText('문서 추가 반영 · Addendum_No1.docx · 판정 2건 변경 · 1건 추가 · 1건 삭제')
  await expect(rows(page)).toHaveCount(4)
  await bar(page).getByRole('button', { name: '변경 항목만 보기' }).click()
  await expect(rows(page)).toHaveCount(3)
  await expect(rows(page).filter({ hasText: '바뀜(개정)' })).toHaveCount(2)
  await expect(rows(page).filter({ hasText: '추가(개정)' })).toHaveCount(1)
  // 바뀐 줄만 보는 중에 판정 상세로 가도 같은 거르기, 꼬리표가 보인다
  await rows(page).first().click()
  await expect(page).toHaveURL(new RegExp(`#/reviews/${ID}/judgments/501\\?rev=1$`))
  await expect(page.locator('.mdpos')).toHaveText('판정 1 / 3')
  await expect(page.locator('.mdh')).toContainText('바뀜(개정)')
})

test('개정 안내 닫기', async ({ page }) => {
  await mock(page)
  await page.goto(`/#/reviews/${ID}`)
  await expect(page.locator('.ttl1')).toContainText('개정 1 반영')
  await bar(page).getByRole('button', { name: '개정 안내 닫기' }).click()
  await expect(bar(page)).toHaveCount(0)
  await page.reload()
  await expect(page.locator('.ttl1')).toContainText('개정 1 반영')
  await expect(rows(page)).toHaveCount(4)
  await expect(bar(page)).toHaveCount(0)
})

test('문서를 더하지 않은 검토는 띠 없음', async ({ page }) => {
  await mock(page, 'ENGINEER_REVIEW', false)
  await page.goto(`/#/reviews/${ID}`)
  await expect(rows(page)).toHaveCount(4)
  await expect(bar(page)).toHaveCount(0)
  await expect(page.locator('.ttl1')).not.toContainText('개정')
})

test('홈에 문서 추가', async ({ page }) => {
  const now = new Date().toISOString()
  const old = new Date(Date.now() - 5 * 86_400_000).toISOString()
  const item = {
    project_name: 'Thai Binh 변전소', review_name: '115·230 kV GIS', customer_name: null, country: null, due_date: null, engineer_id: 1, business_id: null, business_no: null,
    run_id: ID, review_no: 'RV-TEST-REV', engineer_name: '시험 엔지니어', stage: 'ENGINEER_REVIEW', step: null, step_detail: null, step_updated_at: now,
    failed_step: null, error_message: null, started_at: old, finished_at: now, files: 'a.docx, Addendum_No1.docx', requirements: 40, risks: 0,
    deviation_candidates: 2, proposals: 0, approver_id: null, approver: null, requested_by_id: null, requested_by: null, requested_at: null, decision: null, decided_at: null,
    revision: { no: 1, at: now, files: ['Addendum_No1.docx'], changed: 2, added: 1, removed: 0 },
  }
  await page.route('**/api/**', async (r) => {
    const path = new URL(r.request().url()).pathname
    if (path === '/api/users') return r.fulfill({ json: [{ user_id: 1, user_name: '시험 엔지니어', role: 'ENGINEER' }] })
    if (path === '/api/runs') return r.fulfill({ json: [item] })
    if (path.endsWith('/judgment-counts')) return r.fulfill({ json: { by_result: {}, total: 0, unconfirmed: 0, unconfirmed_comply: 0, past_seen: 0, past_differs: 0 } })
    return r.fulfill({ json: [] })
  })
  await page.addInitScript(() => localStorage.setItem('s2w.user', '1'))
  await page.goto('/#/')
  const chg = page.getByRole('region', { name: '어제 이후 바뀐 것' })
  await expect(chg.getByRole('button', { name: /어제 이후 바뀐 것/ })).toContainText('문서 추가 1')
  await chg.getByRole('button', { name: /어제 이후 바뀐 것/ }).click()
  await expect(chg.locator('li')).toContainText('Addendum_No1.docx · 판정 2건 변경 · 1건 추가')
  await expect(chg.getByRole('link', { name: 'RV-TEST-REV 가기' })).toHaveAttribute('href', `#/reviews/${ID}?rev=1`)
})
