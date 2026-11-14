// 화면 타입이 응답 스키마와 맞는지 본다 (명세 api-contract "화면 타입과 서버 스키마 일치").
// 1) openapi.json으로 다시 만든 타입이 저장소의 src/api.gen.ts와 같아야 한다.
// 2) 서버 스키마에 없는 칸을 읽는 코드는 타입 검사에서 실패해야 한다 (검사가 살아 있는지 확인).
import { execFileSync } from 'node:child_process'
import { mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { generate, OUT, SPEC } from './gen-api-types.mjs'

const ROOT = fileURLToPath(new URL('..', import.meta.url))
let failed = false

const fresh = generate(JSON.parse(readFileSync(SPEC, 'utf8')))
if (fresh !== readFileSync(OUT, 'utf8')) {
  console.error('src/api.gen.ts가 openapi.json과 다릅니다. `npm run gen:api`로 다시 만들어 커밋하세요.')
  failed = true
}

const dir = ROOT + 'node_modules/.cache/api-probe/'
mkdirSync(dir, { recursive: true })
writeFileSync(dir + 'probe.ts', "import type { Judgment } from '../../../src/api.gen'\n"
  + 'export const read = (j: Judgment) => j.no_such_field\n')
try {
  execFileSync(process.execPath, [ROOT + 'node_modules/typescript/bin/tsc', '--ignoreConfig', '--noEmit', '--strict',
    '--skipLibCheck', '--target', 'es2022', '--moduleResolution', 'bundler', '--module', 'esnext',
    dir + 'probe.ts'], { stdio: 'pipe' })
  console.error('서버 스키마에 없는 칸(no_such_field)을 읽었는데 타입 검사가 통과했습니다.')
  failed = true
} catch (e) {
  if (!String(e.stdout).includes("'no_such_field'")) {
    console.error('타입 검사가 예상과 다른 이유로 실패했습니다:\n' + e.stdout)
    failed = true
  }
} finally {
  rmSync(dir, { recursive: true, force: true })
}

if (failed) process.exit(1)
console.log('화면 타입이 응답 스키마와 같습니다.')
