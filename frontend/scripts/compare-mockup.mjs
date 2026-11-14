// 목업 대조 (docs/screens/검수표.md). 목업 v4.96 화면과 앱 화면을 같은 너비로 찍어 나란히 저장하고,
// 화면 영역(넓은 블록의 class)이 목업에 있는데 앱에 없는지, 같은 영역의 위아래 순서가 같은지 compare-out/layout.json에 남긴다
// (change add-spec-trace, 명세 spec-verification "목업 배치 점검").
// 쓰는 법: 백엔드(8000)와 `npm run dev`(5173)를 켠 뒤 frontend에서
//   node scripts/compare-mockup.mjs            모든 화면
//   node scripts/compare-mockup.mjs SCR-08 SCR-14   고른 화면만
// 결과: frontend/compare-out/SCR-xx.png (왼쪽 목업, 오른쪽 앱), index.html, layout.json. 커밋하지 않는다.
// 판정 상세(SCR-08-12)는 JUDGMENT_ID, 제품 상세(SCR-16-1)는 PRODUCT_CODE로 고르고, 없으면 RUN_ID의 첫 판정·제품표 첫 제품.
// 검토 상세처럼 실행이 필요한 화면은 RUN_ID·WAIT_ID·FAIL_ID·PROC_ID 환경 변수로 고르고, 없으면 최근 실행에서 단계로 고른다.
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { chromium } from '@playwright/test'

const ROOT = fileURLToPath(new URL('..', import.meta.url))
const MOCKUP = new URL('../../docs/screens/mockup/Spec2Win_목업_v4.96.html', import.meta.url).href
const APP = process.env.APP_URL ?? 'http://localhost:5173'
const OUT = ROOT + 'compare-out/'
const WIDTH = 1600

async function pickRuns() {
  const pick = { RUN_ID: 'ENGINEER_REVIEW', WAIT_ID: 'APPROVAL', FAIL_ID: 'FAILED', PROC_ID: 'PROCESSING' }
  let runs = []
  try { runs = await (await fetch(`${APP}/api/runs?limit=200`)).json() } catch { /* 백엔드가 없으면 실행이 필요한 화면을 건너뛴다 */ }
  const ids = Object.fromEntries(Object.entries(pick).map(([k, stage]) => [k, process.env[k] ?? runs.find((r) => r.stage === stage)?.run_id]))
  let biz = { items: [] }
  try { biz = await (await fetch(`${APP}/api/businesses`)).json() } catch { /* 사업이 없으면 사업 상세를 건너뛴다 */ }
  ids.BUSINESS_NO = process.env.BUSINESS_NO ?? biz.items[0]?.business_no
  ids.JUDGMENT_ID = process.env.JUDGMENT_ID
  if (!ids.JUDGMENT_ID && ids.RUN_ID) {
    try { ids.JUDGMENT_ID = (await (await fetch(`${APP}/api/runs/${ids.RUN_ID}/judgments?limit=1`)).json())[0]?.judgment_id } catch { /* 없으면 건너뜀 */ }
  }
  ids.PRODUCT_CODE = process.env.PRODUCT_CODE
  if (!ids.PRODUCT_CODE) {
    try { ids.PRODUCT_CODE = (await (await fetch(`${APP}/api/products`)).json())[0]?.product_code } catch { /* 없으면 건너뜀 */ }
  }
  return ids
}

/** [SCR, 목업 화면 키, 앱 주소(실행 번호가 없으면 null)] */
function screens(ids) {
  const r = (id, tail = '') => (id ? `/reviews/${id}${tail}` : null)
  return [
    ['SCR-01', 'Login', '/login'], ['SCR-02', 'Loading', r(ids.PROC_ID)], ['SCR-03', 'Home', '/'],
    ['SCR-04', 'Projects', '/projects'], ['SCR-05', 'Project', ids.BUSINESS_NO ? `/projects/${ids.BUSINESS_NO}` : null], ['SCR-06', 'Main', '/reviews'],
    ['SCR-07', 'Register', '/register'], ['SCR-08', 'Detail', r(ids.RUN_ID)],
    ['SCR-08-12', 'JudgeView', ids.JUDGMENT_ID ? r(ids.RUN_ID, `/judgments/${ids.JUDGMENT_ID}`) : null], ['SCR-09', 'Tbe', r(ids.RUN_ID, '/tbe')],
    ['SCR-10', 'Datasheet', r(ids.RUN_ID, '/datasheet')], ['SCR-11', 'Fail', r(ids.FAIL_ID)], ['SCR-12', 'Wait', r(ids.WAIT_ID)],
    ['SCR-13', 'Todo', '/todo'], ['SCR-14', 'Bids', '/bids'], ['SCR-15', 'BidView', '/bids/_'], ['SCR-16', 'Products', '/products'],
    ['SCR-16-1', 'ProductView', ids.PRODUCT_CODE ? `/products/${encodeURIComponent(ids.PRODUCT_CODE)}` : null],
    ['SCR-17', 'Rules', '/rules'], ['SCR-18', 'Phrases', '/phrases'], ['SCR-19', 'Eval', '/eval'], ['SCR-20', 'Team', '/team'],
    ['SCR-21', 'Notice', '/notice'], ['SCR-22', 'SysNotice', '/sysnotice'], ['SCR-23', 'Files', '/files'], ['SCR-24', 'Settings', '/settings'],
  ]
}

/** 화면 영역: 작업 영역(.ws, 없으면 main) 안에서 너비가 30 % 넘고 높이가 20px 넘는 블록의 첫 class와 위쪽 위치.
 * 같은 class는 처음 나온 것만 둔다. 목업과 앱은 같은 CSS class 이름을 쓴다(docs/screens/_프런트원칙.md). */
export async function areasOf(frame) {
  return frame.evaluate(() => {
    const root = document.querySelector('.ws') ?? document.querySelector('main') ?? document.body
    const box = root.getBoundingClientRect()
    const seen = new Map()
    for (const el of root.querySelectorAll('*')) {
      const c = el.classList[0]
      if (!c || seen.has(c)) continue
      const r = el.getBoundingClientRect()
      const st = getComputedStyle(el)
      if (st.display === 'none' || st.visibility === 'hidden' || st.display.startsWith('inline')) continue
      if (r.width > box.width * 0.3 && r.height > 20) seen.set(c, Math.round(r.top - box.top + root.scrollTop))
    }
    // 앱 틀(왼쪽 메뉴·머리글)을 감싸는 class는 영역으로 치지 않는다
    for (const c of ['layout', 'main']) seen.delete(c)
    return [...seen].sort((a, b) => a[1] - b[1]).map(([c]) => c)
  })
}

/** 목업 영역 중 앱에 없는 것과, 둘 다 있는 영역의 순서가 같은지 */
// 목업과 앱이 같은 영역을 다른 class로 쓰는 곳 (목업 class → 앱 class). 쪽 넘기기는 앱 공통 부품 Pager(src/ui)
export const SAME_AREA = { pgx: 'pager' }

export function compareAreas(mockRaw, app) {
  const mock = mockRaw.map((c) => SAME_AREA[c] ?? c)
  const missing = mock.filter((c) => !app.includes(c))
  const common = mock.filter((c) => app.includes(c))
  const appOrder = app.filter((c) => common.includes(c))
  const sameOrder = common.every((c, i) => appOrder[i] === c)
  return { missing, extra: app.filter((c) => !mock.includes(c)), common, sameOrder, ok: missing.length === 0 && sameOrder }
}

async function shootMockup(browser, key, file) {
  const pg = await browser.newPage({ viewport: { width: WIDTH, height: 1000 } })
  await pg.route(/^https?:\/\//, (route) => route.abort())   // 목업은 바깥 주소를 부르지 않게 한다
  await pg.goto(`${MOCKUP}#${key}`)
  await pg.waitForTimeout(2500)
  await pg.evaluate((n) => window.__go?.(n, ''), key)
  await pg.waitForTimeout(1500)
  const frame = pg.frames().find((f) => f !== pg.mainFrame()) ?? pg.mainFrame()
  const h = await frame.evaluate(() => Math.max(document.querySelector('.ws')?.scrollHeight ?? 0, document.body.scrollHeight))
  await pg.setViewportSize({ width: WIDTH, height: Math.min(h + 80, 3000) })
  await pg.waitForTimeout(800)
  await pg.screenshot({ path: file })
  const areas = await areasOf(frame)
  await pg.close()
  return areas
}

async function shootApp(browser, path, file) {
  const pg = await browser.newPage({ viewport: { width: WIDTH, height: 1000 } })
  await pg.addInitScript(() => localStorage.setItem('s2w.user', '1'))
  await pg.goto(`${APP}/#${path}`)
  await pg.waitForTimeout(2500)
  // 목업처럼 창 높이를 화면 길이에 맞춰 왼쪽 메뉴도 끝까지 보이게 한다
  const h = await pg.evaluate(() => Math.max(document.querySelector('.ws')?.scrollHeight ?? 0, document.body.scrollHeight))
  await pg.setViewportSize({ width: WIDTH, height: Math.min(h + 80, 3000) })
  await pg.waitForTimeout(800)
  await pg.screenshot({ path: file })
  const areas = await areasOf(pg.mainFrame())
  await pg.close()
  return areas
}

// 빈 페이지에서는 file:// 그림을 못 읽어 data 주소로 넣는다
const dataUrl = (file) => 'data:image/png;base64,' + readFileSync(file).toString('base64')

/** 두 장을 한 장으로 붙인다 (왼쪽 목업, 오른쪽 앱) */
async function sideBySide(browser, scr, key, path, mock, app, file) {
  const pg = await browser.newPage({ viewport: { width: 1640, height: 800 } })
  await pg.setContent(`<body style="margin:0;font:14px sans-serif;background:#fff">
    <div style="display:flex;gap:16px;padding:8px;align-items:flex-start">
      <figure style="margin:0;width:800px"><figcaption><b>${scr}</b> 목업 ${key}</figcaption><img src="${dataUrl(mock)}" style="width:800px;border:1px solid #ccc"></figure>
      <figure style="margin:0;width:800px"><figcaption><b>${scr}</b> 앱 #${path}</figcaption><img src="${dataUrl(app)}" style="width:800px;border:1px solid #ccc"></figure>
    </div></body>`)
  await pg.waitForLoadState('load')
  await pg.screenshot({ path: file, fullPage: true })
  await pg.close()
}

if (process.argv[1] !== fileURLToPath(import.meta.url)) {
  // 다른 곳(scripts/trace.test.mjs)에서 불러 쓸 때는 화면을 찍지 않는다
} else {
const only = process.argv.slice(2)
mkdirSync(OUT + 'raw', { recursive: true })
const ids = await pickRuns()
const list = screens(ids).filter(([scr]) => !only.length || only.includes(scr))
const browser = await chromium.launch(process.env.PW_CHROMIUM ? { executablePath: process.env.PW_CHROMIUM } : {})
const rows = []
const layout = {}
for (const [scr, key, path] of list) {
  if (!path) { console.log(`${scr} ${key}: 건너뜀 (맞는 단계의 실행이 없음)`); rows.push(`<li>${scr} ${key}: 건너뜀</li>`); continue }
  const mock = `${OUT}raw/${scr}-mock.png`
  const app = `${OUT}raw/${scr}-app.png`
  const mockAreas = await shootMockup(browser, key, mock)
  const appAreas = await shootApp(browser, path, app)
  await sideBySide(browser, scr, key, path, mock, app, `${OUT}${scr}.png`)
  const cmp = compareAreas(mockAreas, appAreas)
  layout[scr] = { key, path, ...cmp, mock: mockAreas, app: appAreas }
  const mark = cmp.ok ? '배치 같음' : `빠진 영역 ${cmp.missing.join(', ') || '없음'}${cmp.sameOrder ? '' : ' · 순서 다름'}`
  rows.push(`<li><a href="${scr}.png">${scr} ${key}</a> ↔ #${path} — ${mark}</li>`)
  console.log(`${scr} ${key} ↔ #${path} — ${mark}`)
}
await browser.close()
writeFileSync(OUT + 'index.html', `<!doctype html><meta charset="utf-8"><title>목업 대조</title><h1>목업 v4.96 ↔ 앱</h1><ul>${rows.join('')}</ul>`)
writeFileSync(OUT + 'layout.json', JSON.stringify(layout, null, 2))
}
