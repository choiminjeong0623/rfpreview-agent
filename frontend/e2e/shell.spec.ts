import { expect, test } from '@playwright/test'

// 명세 review-workspace "앱 틀과 화면 주소"의 Scenario (change update-app-shell).
// 백엔드(8000)와 `npm run dev`(5173)만 있으면 되고 RFP 원문은 필요 없다.

test('메뉴로 화면 이동', async ({ page }) => {
  await page.goto('/#/reviews')
  const nav = page.getByRole('navigation', { name: '메뉴' })
  await expect(nav.getByRole('link', { name: 'RFP 검토' })).toHaveAttribute('aria-current', 'page')

  await nav.getByRole('button', { name: '지식 관리' }).click()
  await nav.getByRole('link', { name: '제품 관리' }).click()
  await expect(page).toHaveURL(/#\/products$/)
  await expect(nav.getByRole('link', { name: '제품 관리' })).toHaveAttribute('aria-current', 'page')
  await expect(page.getByRole('navigation', { name: '현재 위치' })).toContainText('기준 데이터')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('제품표')
  await expect(page.getByRole('navigation', { name: '현재 위치' }).getByRole('link', { name: '홈' })).toBeVisible()

  // 주소로 바로 열어도 같은 화면과 메뉴가 켜진다
  await page.goto('/#/todo')
  await expect(nav.getByRole('link', { name: '협조 요청' })).toHaveAttribute('aria-current', 'page')
  await expect(page.getByRole('button', { name: 'RFP 관리' })).toHaveAttribute('aria-expanded', 'true')
})

test('정답지·채점은 시스템 관리 아래', async ({ page }) => {
  // change update-system-menu. 예전 주소 #/eval 그대로 열린다
  await page.goto('/#/eval')
  const nav = page.getByRole('navigation', { name: '메뉴' })
  await expect(nav.getByRole('button', { name: '시스템 관리' })).toHaveAttribute('aria-expanded', 'true')
  await expect(nav.getByRole('link', { name: '정답지·채점' })).toHaveAttribute('aria-current', 'page')
  await expect(page.getByRole('navigation', { name: '현재 위치' })).toContainText('시스템 관리')
  await expect(page.locator('#sbk-kn').getByRole('link', { name: '정답지·채점' })).toHaveCount(0)
})

test('실행 기록도 시스템 관리 아래', async ({ page }) => {
  // change update-runlog-menu. 주소 #/runlog 그대로
  await page.goto('/#/runlog')
  const nav = page.getByRole('navigation', { name: '메뉴' })
  await expect(nav.getByRole('button', { name: '시스템 관리' })).toHaveAttribute('aria-expanded', 'true')
  await expect(nav.getByRole('link', { name: '실행 기록' })).toHaveAttribute('aria-current', 'page')
  const crumb = page.getByRole('navigation', { name: '현재 위치' })
  await expect(crumb).toContainText('시스템 관리')
  await expect(crumb).not.toContainText('시스템 관리 관리')
  await expect(page.locator('#sbk-kn').getByRole('link', { name: '실행 기록' })).toHaveCount(0)
})

test('메뉴 접기', async ({ page }) => {
  await page.goto('/#/')
  await page.getByRole('button', { name: '메뉴 접기' }).click()
  await expect(page.locator('.app')).toHaveClass(/mini/)
  await page.reload()
  await expect(page.locator('.app')).toHaveClass(/mini/)   // 접은 상태를 기억한다
  await page.getByRole('button', { name: '메뉴 펼치기' }).click()
  await expect(page.locator('.app')).not.toHaveClass(/mini/)
})

test('사용자 바꾸기', async ({ page }) => {
  await page.goto('/#/reviews')
  const chip = page.getByRole('button', { name: '사용자 바꾸기' })
  await chip.click()
  await page.getByRole('button', { name: /기본 승인자/ }).click()
  await expect(chip).toContainText('기본 승인자')
  await expect(chip).toContainText('승인자')
  await page.reload()
  await expect(chip).toContainText('기본 승인자')   // 고른 사용자를 기억한다
})

test('로그아웃', async ({ page }) => {
  // change add-logout-button. 고른 사용자를 지우고 예시 로그인 화면으로 간다
  await page.goto('/#/reviews')
  const chip = page.getByRole('button', { name: '사용자 바꾸기' })
  await chip.click()
  await page.getByRole('button', { name: /기본 승인자/ }).click()
  await expect(chip).toContainText('기본 승인자')
  await chip.click()
  await page.getByRole('button', { name: '로그아웃' }).click()
  await expect(page).toHaveURL(/#\/login$/)
  await page.getByLabel('사번 또는 회사 이메일').fill('20261234')
  await page.getByLabel('비밀번호', { exact: true }).fill('example')
  await page.getByRole('button', { name: '로그인', exact: true }).click()
  await expect(page).toHaveURL(/#\/$/, { timeout: 10_000 })
  await expect(page.getByRole('button', { name: '사용자 바꾸기' })).not.toContainText('기본 승인자')
})

test('알림은 예시로 보인다', async ({ page }) => {
  await page.goto('/#/reviews')
  await page.getByRole('button', { name: /알림 \d건/ }).click()
  const panel = page.getByRole('dialog', { name: '알림' })
  await expect(panel).toContainText('예시')
  await panel.getByRole('button', { name: '모두 읽음으로' }).click()
  await expect(page.getByRole('button', { name: '알림 0건' })).toBeVisible()
})

test('역할별 판과 판 기록', async ({ page }) => {
  // change add-prompt-view. 백엔드 GET /api/prompts가 필요하다
  await page.goto('/#/prompts')
  const nav = page.getByRole('navigation', { name: '메뉴' })
  await expect(nav.getByRole('button', { name: '시스템 관리' })).toHaveAttribute('aria-expanded', 'true')
  await expect(nav.getByRole('link', { name: '프롬프트 관리' })).toHaveAttribute('aria-current', 'page')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('프롬프트 관리')
  await page.getByRole('row', { name: /유형/ }).first().click()
  await expect(page.getByText('판 기록')).toBeVisible()
  await expect(page.getByText('지금 판').first()).toBeVisible()
})
