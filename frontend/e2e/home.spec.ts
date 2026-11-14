import { readFileSync } from 'node:fs'
import { expect, test, type APIRequestContext } from '@playwright/test'
import { ENGINEER } from './helpers'

// SCR-03 홈. 합성 사양서(tests/docx_factory.build_gis_spec)는 품질 담당에게 형식시험 요청을 보내므로 "협조 대기" 열에 간다.
const DOCX = new URL('./fixtures/synthetic_154kV_GIS_spec.docx', import.meta.url)

function today(): string {
  const d = new Date()
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

async function dueToday(request: APIRequestContext, project: string, scope: string) {
  const res = await request.post('/api/runs', {
    multipart: {
      files: { name: 'synthetic_154kV_GIS_spec.docx', mimeType: 'application/octet-stream', buffer: readFileSync(DOCX) },
      // 문서 목록에 없는 문서라 묶음을 정해 보낸다 (reject-unjudged-registration)
      choices: JSON.stringify({ 'synthetic_154kV_GIS_spec.docx': { bundle: 'B' } }),
      project_name: project, review_name: scope, due_date: today(), actor_id: String(ENGINEER),
    },
  })
  const run = await res.json() as { run_id: number; review_no: string }
  await expect.poll(async () => (await (await request.get(`/api/runs/${run.run_id}`)).json()).stage,
    { timeout: 60_000 }).toBe('ENGINEER_REVIEW')
  return run
}

// Scenario: 내 업무 칸으로 강조 / 사업별 보기
test('내 업무와 단계별 카드', async ({ page, request }) => {
  const scope = `홈 카드 ${Date.now()}`
  const run = await dueToday(request, '예시 변전소 H', scope)
  await page.goto('/#/')
  await page.getByRole('button', { name: '단계별' }).click()   // v4.96: 처음 보기는 일정
  const col = page.getByLabel('협조 대기', { exact: true })
  const card = col.locator('.bd-card', { hasText: run.review_no })
  await expect(card).toContainText(scope)
  await expect(card).toContainText('D-Day')
  await expect(card).toContainText(/협조 미확인 \d+건/)
  await expect(page.locator('.qsum button', { hasText: '3일 내 마감' }).locator('b')).not.toHaveText('0')

  // 내 업무 칸을 누르면 그 조건이 아닌 카드는 흐려지고 필터 칩이 보인다
  await page.locator('.qsum button', { hasText: '결재 대기' }).click()
  await expect(page.getByRole('button', { name: '필터 해제' })).toContainText('결재 대기')
  await expect(card).toHaveClass(/dim/)
  await page.getByRole('button', { name: '필터 해제' }).click()
  await expect(card).not.toHaveClass(/dim/)

  // 사업별로 보면 사업 이름 아래에 카드가 모인다
  await page.getByRole('button', { name: '사업별' }).click()
  const group = page.locator('.bpg', { hasText: '예시 변전소 H' })
  await expect(group.locator('.bd-card', { hasText: run.review_no })).toContainText('협조 대기')
})

test('분석 실패 알림', async ({ page }) => {
  await page.route('**/api/runs?limit=200', async (route) => {
    const res = await route.fetch()
    const rows = await res.json() as Record<string, unknown>[]
    const failed = { ...rows[0], run_id: 999001, review_no: 'RV-2026-901', project_name: '예시 실패', review_name: '배전반',
      engineer_id: ENGINEER, stage: 'FAILED', failed_step: 'risks', error_message: '언어 모델이 응답하지 않았습니다.', finished_at: new Date().toISOString() }
    await route.fulfill({ response: res, json: [failed, ...rows] })
  })
  await page.goto('/#/')
  const alert = page.getByRole('alert').filter({ hasText: '분석이 멈췄습니다' })
  await expect(alert).toContainText('RV-2026-901 예시 실패 · 배전반 분석이 멈췄습니다')
  await expect(alert).toContainText('위험 조건 찾기')
  await expect(alert.getByRole('link', { name: '오류 내용 보기' })).toHaveAttribute('href', '#/reviews/999001')
  await page.getByRole('button', { name: '단계별' }).click()
  // 끼워 넣은 실패 검토 카드만 본다 (로컬 DB에 실패 검토가 더 있어도 되게)
  await expect(page.getByLabel('분석 중', { exact: true }).locator('.bd-card.fail', { hasText: 'RV-2026-901' })).toContainText('분석 실패')
  await alert.getByRole('button', { name: '알림 닫기' }).click()
  await expect(alert).toBeHidden()
})

test('팀 공유와 행사 예시', async ({ page }) => {
  await page.goto('/#/')
  const team = page.locator('.hm-box')
  await expect(team.locator('.hm-row', { hasText: '기본 승인자' })).toBeVisible()
  await expect(team.locator('.hm-row', { hasText: '기본 품질 담당' })).toContainText('협조')
  await page.getByRole('tab', { name: '공지사항' }).click()
  await expect(team.getByText('예시 화면')).toBeVisible()
  await team.getByRole('button', { name: /주간 회의/ }).click()
  await expect(team.getByText(/수요일 10:00로 옮깁니다\./)).toBeVisible()
  const ev = page.locator('section', { has: page.getByRole('heading', { name: '교육 · 봉사 · 행사' }) })
  await expect(ev.getByText('1–3 / 8')).toBeVisible()
  await ev.getByRole('button', { name: '다음 행사' }).click()
  await expect(ev.getByText('2–4 / 8')).toBeVisible()
})
