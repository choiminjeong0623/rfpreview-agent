// 추적표 만들기 (change add-spec-trace). FR → OpenSpec 시나리오 → 화면(SCR) 수용 기준 → 구현 컴포넌트 → 테스트를 한 표로 잇는다.
// 쓰는 법 (frontend에서):
//   npm run trace         docs/추적표.md 를 다시 쓴다
//   npm run check:trace   다시 만든 내용이 파일과 다르거나 설정이 틀리면 실패 (CI)
// 잇는 규칙: 시나리오·수용 기준 이름 = 백엔드 테스트 docstring "Scenario: A / B — …"의 이름, e2e test('이름')과 바로 위 "// Scenario: A / B",
// 도구 테스트(scripts/*.test.mjs) test('Scenario: 이름').
// 같은 입력이면 같은 표다(날짜·시각을 넣지 않는다).
import { existsSync, readFileSync, readdirSync, writeFileSync } from 'node:fs'
import { basename, join } from 'node:path'
import { fileURLToPath } from 'node:url'

export const ROOT = fileURLToPath(new URL('../../', import.meta.url))
const OUT = 'docs/추적표.md'

const read = (root, p) => readFileSync(join(root, p), 'utf8')
const list = (root, dir, re) => existsSync(join(root, dir)) ? readdirSync(join(root, dir)).filter((f) => re.test(f)).sort() : []
const lineOf = (text, index) => text.slice(0, index).split('\n').length

/** 명세서 1장 표: | FR-01 | 문서 분류 | Must | … */
export function parseFrs(text) {
  const out = []
  for (const m of text.matchAll(/^\|\s*(FR-\d+)\s*\|\s*([^|]+?)\s*\|\s*(Must|Should|Could)\s*\|/gm)) {
    if (!out.some((f) => f.id === m[1])) out.push({ id: m[1], name: m[2], priority: m[3] })
  }
  return out
}

/** OpenSpec 확정 스펙의 시나리오 */
export function parseScenarios(text) {
  return [...text.matchAll(/^#### Scenario:\s*(.+?)\s*$/gm)].map((m) => m[1])
}

/** 백엔드 테스트: def test_… 바로 아래 docstring 첫 줄의 "Scenario: A / B — 설명" */
export function parsePyTests(text, file) {
  const out = []
  for (const m of text.matchAll(/^\s*def (test_\w+)\([^)]*\)[^:]*:\s*\n\s*(?:"""|''')([\s\S]*?)(?:"""|''')/gm)) {
    const doc = m[2]
    const line = lineOf(text, m.index + m[0].indexOf('def '))
    // "Scenario: A / B — 설명", "Scenario: A · Scenario: B — 설명", 끝의 "(CR-11)" 같은 덧붙임은 뺀 이름도 잇는다
    for (const s of doc.matchAll(/Scenario:\s*((?:(?!Scenario:)[^\n])+)/g)) {
      const head = s[1].split(/\s+—(?:\s+|$)|\s+--\s+|\s+·\s*$/)[0]
      for (const name of head.split(' / ')) {
        const n = name.trim().replace(/[.。]$/, '')
        if (!n) continue
        out.push({ name: n, file, line })
        const bare = n.replace(/\s*\([^()]*\)$/, '')
        if (bare !== n) out.push({ name: bare, file, line })
      }
    }
  }
  return out
}

/** e2e: test('이름', …). 바로 위 줄의 "// Scenario: A / B" 주석은 같은 테스트의 다른 이름이다 */
export function parseE2eTests(text, file) {
  const out = []
  for (const m of text.matchAll(/^\s*test(?:\.(?:skip|fixme|only))?\(\s*(['"`])(.+?)\1/gm)) {
    const at = m.index + m[0].indexOf('test')
    const line = lineOf(text, at)
    out.push({ name: m[2].trim(), file, line })
    const before = text.slice(0, m.index).split('\n').slice(-2).join('\n')
    const alias = before.match(/\/\/\s*Scenario:\s*([^\n]+)\s*$/)
    if (alias) for (const n of alias[1].split(' / ')) if (n.trim()) out.push({ name: n.trim(), file, line })
  }
  return out
}

/** 화면 명세 수용 기준: "- **Given** …, **When** …, **Then** …. (이름)" */
export function parseCriteria(text) {
  const out = []
  for (const line of text.split('\n')) {
    if (!line.includes('**Given**')) continue
    const m = line.trim().match(/\(([^()]+)\)\s*$/)
    out.push({ name: m ? m[1].trim() : null, text: line.replace(/^\s*-\s*/, '').replace(/\s*\([^()]+\)\s*$/, '') })
  }
  return out
}

/** 저장소에서 모든 입력을 읽는다 */
export function load(root = ROOT) {
  const config = JSON.parse(read(root, 'docs/추적_연결.json'))
  const frs = parseFrs(read(root, 'docs/reference/기능요구사항명세서_v1.md'))
  const specs = {}
  for (const cap of list(root, 'openspec/specs', /^[a-z-]+$/)) {
    const p = `openspec/specs/${cap}/spec.md`
    if (existsSync(join(root, p))) specs[cap] = parseScenarios(read(root, p))
  }
  const tests = [
    ...list(root, 'backend/tests', /^test_.*\.py$/).flatMap((f) => parsePyTests(read(root, `backend/tests/${f}`), `backend/tests/${f}`)),
    ...list(root, 'frontend/e2e', /\.spec\.ts$/).flatMap((f) => parseE2eTests(read(root, `frontend/e2e/${f}`), `frontend/e2e/${f}`)),
    // 도구 테스트(node --test): test('Scenario: 이름', …)
    ...list(root, 'frontend/scripts', /\.test\.mjs$/).flatMap((f) => parseE2eTests(read(root, `frontend/scripts/${f}`), `frontend/scripts/${f}`))
      .filter((t) => t.name.startsWith('Scenario: ')).map((t) => ({ ...t, name: t.name.slice('Scenario: '.length) })),
  ]
  const screens = {}
  for (const f of list(root, 'docs/screens', /^SCR-[\d-]+-.+\.md$/)) {
    const id = f.match(/^(SCR-\d+(?:-\d+)?)-/)[1]
    const text = read(root, `docs/screens/${f}`)
    screens[id] = { file: `docs/screens/${f}`, title: f.replace(/^SCR-[\d-]+?-(?=\D)/, '').replace(/\.md$/, ''), criteria: parseCriteria(text) }
  }
  return { config, frs, specs, tests, screens, exists: (p) => existsSync(join(root, 'frontend/src', p)) }
}

const SCR_ORDER = (a, b) => {
  const k = (s) => s.replace('SCR-', '').split('-').map(Number)
  const [x, y] = [k(a), k(b)]
  return x[0] - y[0] || (x[1] ?? -1) - (y[1] ?? -1)
}

/** 입력에서 추적표 글과 오류 목록을 만든다 */
export function build({ config, frs, specs, tests, screens, exists }) {
  const errors = []
  const byName = new Map()
  for (const t of tests) byName.set(t.name, [...(byName.get(t.name) ?? []), t])
  const linkOf = (name) => (name ? byName.get(name) ?? [] : [])
  const loc = (t) => `\`${t.file.replace(/^(backend|frontend)\//, '')}:${t.line}\``
  const pct = (a, b) => (b ? `${Math.round((a / b) * 100)} %` : '—')
  const uniqFiles = (ts) => [...new Set(ts.map((t) => t.file.replace(/^(backend|frontend)\//, '')))].sort()

  // 설정 검사
  const caps = Object.keys(specs)
  const used = new Set()
  for (const [fr, v] of Object.entries(config.fr)) {
    if (!frs.some((f) => f.id === fr)) errors.push(`설정의 ${fr}가 명세서 FR 표에 없습니다`)
    for (const c of v.specs) { used.add(c); if (!specs[c]) errors.push(`${fr}의 capability "${c}"가 openspec/specs에 없습니다`) }
  }
  for (const [g, cs] of Object.entries(config.common)) for (const c of cs) { used.add(c); if (!specs[c]) errors.push(`공통 "${g}"의 capability "${c}"가 없습니다`) }
  for (const c of caps) if (!used.has(c)) errors.push(`capability "${c}"가 설정(fr·common)에 없습니다`)
  for (const f of frs) if (!config.fr[f.id]) errors.push(`명세서 ${f.id}가 설정 fr에 없습니다`)
  for (const [scr, v] of Object.entries(config.screens)) {
    for (const p of v.components) if (!exists(p)) errors.push(`${scr} 컴포넌트 파일이 없습니다: frontend/src/${p}`)
    for (const fr of v.fr) if (!config.fr[fr]) errors.push(`${scr}의 ${fr}가 설정 fr에 없습니다`)
  }
  for (const scr of Object.keys(screens)) if (!config.screens[scr]) errors.push(`화면 명세 ${scr}가 설정 screens에 없습니다`)
  for (const [flow, fs] of Object.entries(config.flows ?? {})) {
    if (!linkOf(flow).length) errors.push(`핵심 흐름 "${flow}"와 이름이 같은 테스트가 없습니다`)
    for (const fr of fs) if (!config.fr[fr]) errors.push(`핵심 흐름 "${flow}"의 ${fr}가 설정 fr에 없습니다`)
  }

  // 시나리오·수용 기준 ↔ 테스트
  const capStat = Object.fromEntries(caps.map((c) => {
    const rows = specs[c].map((name) => ({ name, tests: linkOf(name) }))
    return [c, { rows, done: rows.filter((r) => r.tests.length).length }]
  }))
  const scrIds = Object.keys(config.screens).sort(SCR_ORDER)
  const scrStat = Object.fromEntries(scrIds.map((s) => {
    const rows = (screens[s]?.criteria ?? []).map((c) => ({ ...c, tests: linkOf(c.name) }))
    return [s, { rows, done: rows.filter((r) => r.tests.length).length }]
  }))
  for (const f of frs) {
    const n = (config.fr[f.id]?.specs ?? []).reduce((s, c) => s + (specs[c]?.length ?? 0), 0)
    const m = scrIds.filter((s) => config.screens[s].fr.includes(f.id)).reduce((s, x) => s + scrStat[x].rows.length, 0)
    if (!n && !m) errors.push(`${f.id}에 이어진 시나리오·수용 기준이 하나도 없습니다`)
  }

  const allSc = caps.reduce((s, c) => s + capStat[c].rows.length, 0)
  const doneSc = caps.reduce((s, c) => s + capStat[c].done, 0)
  const allAc = scrIds.reduce((s, x) => s + scrStat[x].rows.length, 0)
  const doneAc = scrIds.reduce((s, x) => s + scrStat[x].done, 0)

  const L = []
  L.push('# 추적표', '')
  L.push('> 자동 생성 파일이다. 손으로 고치지 않는다. `cd frontend && npm run trace`로 다시 만들고, CI(`npm run check:trace`)가 낡았는지 검사한다 (change `add-spec-trace`).')
  L.push('> 연결 설정은 `docs/추적_연결.json`. 시나리오·수용 기준과 테스트는 **이름이 같으면** 잇는다: 백엔드 테스트 docstring `Scenario: 이름`, e2e `test(\'이름\')`와 바로 위 `// Scenario: 이름`, 도구 테스트 `test(\'Scenario: 이름\')`, 화면 명세 수용 기준 줄 끝 `(이름)`.', '')
  L.push(`- 명세서 FR ${frs.length}개, OpenSpec capability ${caps.length}개`)
  L.push(`- OpenSpec 시나리오 ${allSc}개 중 테스트가 있는 것 **${doneSc}개 (${pct(doneSc, allSc)})**`)
  L.push(`- 화면 명세 수용 기준 ${allAc}개 중 e2e가 있는 것 **${doneAc}개 (${pct(doneAc, allAc)})**`)
  L.push(`- 테스트: 백엔드 ${new Set(tests.filter((t) => t.file.startsWith('backend')).map((t) => t.file)).size}개 파일, e2e ${new Set(tests.filter((t) => t.file.startsWith('frontend/e2e')).map((t) => t.file)).size}개 파일, 도구 ${new Set(tests.filter((t) => t.file.startsWith('frontend/scripts')).map((t) => t.file)).size}개 파일`, '')

  L.push('## 1. FR → 스펙 → 화면 → 컴포넌트 → 테스트', '')
  L.push('| FR | 이름 | 우선 | 스펙 (시나리오 테스트 / 전체) | 화면 (수용 기준 e2e / 전체) | 구현 컴포넌트 (`frontend/src/`) | 테스트 파일 |')
  L.push('|---|---|---|---|---|---|---|')
  for (const f of frs) {
    const cs = config.fr[f.id]?.specs ?? []
    const ss = scrIds.filter((s) => config.screens[s].fr.includes(f.id))
    const flows = Object.entries(config.flows ?? {}).filter(([, fs]) => fs.includes(f.id)).map(([n]) => n)
    const ts = [...cs.flatMap((c) => capStat[c]?.rows.flatMap((r) => r.tests) ?? []),
      ...ss.flatMap((s) => scrStat[s].rows.flatMap((r) => r.tests)), ...flows.flatMap(linkOf)]
    const comps = [...new Set(ss.flatMap((s) => config.screens[s].components))].sort()
    L.push(`| ${f.id} | ${f.name} | ${f.priority} | ${cs.map((c) => `\`${c}\` ${capStat[c]?.done ?? 0} / ${capStat[c]?.rows.length ?? 0}`).join('<br>') || '—'} | ${ss.map((s) => `${s} ${scrStat[s].done} / ${scrStat[s].rows.length}`).join('<br>') || '—'} | ${comps.map((c) => `\`${c}\``).join('<br>') || '—'} | ${uniqFiles(ts).map((x) => `\`${x}\``).join('<br>') || '—'}${flows.length ? `<br>핵심 흐름: ${flows.join(', ')}` : ''} |`)
  }
  L.push('')

  L.push('## 2. FR 밖 공통 스펙', '')
  L.push('| 묶음 | 스펙 (시나리오 테스트 / 전체) | 테스트 파일 |', '|---|---|---|')
  for (const [g, cs] of Object.entries(config.common)) {
    const ts = cs.flatMap((c) => capStat[c]?.rows.flatMap((r) => r.tests) ?? [])
    L.push(`| ${g} | ${cs.map((c) => `\`${c}\` ${capStat[c]?.done ?? 0} / ${capStat[c]?.rows.length ?? 0}`).join('<br>')} | ${uniqFiles(ts).length}개 파일 |`)
  }
  L.push('')

  L.push('## 3. 화면 → 수용 기준 → e2e', '')
  L.push('| 화면 | 명세 | FR | 구현 컴포넌트 (`frontend/src/`) | 수용 기준 e2e / 전체 |', '|---|---|---|---|---|')
  for (const s of scrIds) {
    const doc = screens[s]
    L.push(`| ${s} | ${doc ? `\`${doc.file.replace('docs/screens/', '')}\`` : '명세 없음'} | ${config.screens[s].fr.join(', ') || '—'} | ${config.screens[s].components.map((c) => `\`${c}\``).join('<br>')} | ${scrStat[s].done} / ${scrStat[s].rows.length} |`)
  }
  L.push('')
  for (const s of scrIds) {
    if (!scrStat[s].rows.length) continue
    L.push(`<details><summary>${s} ${screens[s].title} — ${scrStat[s].done} / ${scrStat[s].rows.length}</summary>`, '')
    L.push('| 수용 기준 | 이름 | 테스트 |', '|---|---|---|')
    for (const r of scrStat[s].rows) L.push(`| ${r.text.replace(/\|/g, '\\|')} | ${r.name ?? '(이름 없음)'} | ${r.tests.map(loc).join('<br>') || '**없음**'} |`)
    L.push('', '</details>', '')
  }

  L.push('## 4. 스펙 시나리오 → 테스트', '')
  for (const c of caps) {
    const st = capStat[c]
    L.push(`<details><summary><code>${c}</code> — ${st.done} / ${st.rows.length}</summary>`, '')
    L.push('| 시나리오 | 테스트 |', '|---|---|')
    for (const r of st.rows) L.push(`| ${r.name.replace(/\|/g, '\\|')} | ${r.tests.map(loc).join('<br>') || '**없음**'} |`)
    L.push('', '</details>', '')
  }

  L.push('## 5. 검증 안 된 것', '')
  L.push('이름이 같은 테스트가 없는 시나리오·수용 기준. 테스트를 더하거나, 이미 있는 테스트의 이름·docstring을 맞춘다.', '')
  L.push('| 어디 | 이름 |', '|---|---|')
  for (const c of caps) for (const r of capStat[c].rows) if (!r.tests.length) L.push(`| \`${c}\` | ${r.name} |`)
  for (const s of scrIds) for (const r of scrStat[s].rows) if (!r.tests.length) L.push(`| ${s} | ${r.name ?? `(이름 없음) ${r.text.slice(0, 40)}…`} |`)
  L.push('')
  return { text: L.join('\n'), errors, stats: { allSc, doneSc, allAc, doneAc } }
}

/** 파일에 있는 추적표(now)가 다시 만든 것(text)과 다르면 안내 문장, 같으면 null */
export function stale(now, text) {
  return now === text ? null : `${OUT}가 지금 스펙·테스트와 다릅니다. cd frontend && npm run trace 로 다시 만들어 커밋하세요`
}

if (process.argv[1] && basename(process.argv[1]) === 'trace.mjs') {
  const check = process.argv.includes('--check')
  const { text, errors, stats } = build(load())
  const now = existsSync(join(ROOT, OUT)) ? readFileSync(join(ROOT, OUT), 'utf8') : ''
  if (check && stale(now, text)) errors.push(stale(now, text))
  if (!check) writeFileSync(join(ROOT, OUT), text)
  console.log(`시나리오 ${stats.doneSc} / ${stats.allSc}, 화면 수용 기준 ${stats.doneAc} / ${stats.allAc}`)
  if (errors.length) { for (const e of errors) console.error('추적표: ' + e); process.exit(1) }
  console.log(check ? '추적표가 지금 스펙·테스트와 같습니다.' : `${OUT}를 다시 썼습니다.`)
}
