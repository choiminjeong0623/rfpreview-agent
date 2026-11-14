// 우리가 쓴 CSS·화면 코드에 색 값을 직접 쓰지 않았는지 본다 (add-ui-foundation, _프런트원칙.md 5장).
// 목업 CSS(src/mockup)와 토큰 파일(src/styles/tokens.css)은 뺀다. 색은 var(--c-…) 토큰으로 쓴다.
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

// 경로에 한글이 있어도 되게 (pathname은 %EA… 그대로라 폴더를 못 찾는다)
const root = fileURLToPath(new URL('../src', import.meta.url))
const skip = [join(root, 'mockup'), join(root, 'styles', 'tokens.css'), join(root, 'api.gen.ts')]
const color = /#[0-9A-Fa-f]{6}\b|#[0-9A-Fa-f]{3}\b(?![0-9A-Za-z-])|rgba?\(/g
const bad = []

function walk(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (skip.some((s) => p === s || p.startsWith(s + '/'))) continue
    if (statSync(p).isDirectory()) { walk(p); continue }
    if (!/\.(css|tsx?)$/.test(name)) continue
    readFileSync(p, 'utf8').split('\n').forEach((line, i) => {
      // CSS·코드 주석 줄과 JSON 자료(예: productDocs.json)는 보지 않는다
      const code = line.replace(/\/\*.*?\*\/|\/\/.*$/g, '')
      // TS 안의 색은 문자열('…')만 본다 (예: id #123 같은 글자는 빼기 위해)
      const hits = /\.css$/.test(name) ? code.match(color) : code.match(/['"`](?:#[0-9A-Fa-f]{3,6}|rgba?\()/g)
      if (hits) bad.push(`${relative(root, p)}:${i + 1}  ${hits.join(' ')}`)
    })
  }
}

walk(root)
if (bad.length) {
  console.error(`색을 직접 쓴 곳 ${bad.length}곳 — src/styles/tokens.css의 var(--…)로 바꾸세요:\n` + bad.join('\n'))
  process.exit(1)
}
console.log('토큰 검사 통과')
