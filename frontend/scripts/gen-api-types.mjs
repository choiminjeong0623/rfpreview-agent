// 응답 스키마(openapi.json)에서 화면 타입(src/api.gen.ts)을 만든다 (change update-api-contract).
// 쓰는 법: `npm run gen:api` (백엔드 응답 모델 → openapi.json → 이 스크립트). 만든 파일은 커밋한다.
// openapi-typescript는 TypeScript 5만 받아(이 저장소는 6) 쓰지 않고, 이 저장소가 쓰는 스키마 모양만 옮긴다.
import { readFileSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const ROOT = fileURLToPath(new URL('..', import.meta.url))
export const SPEC = ROOT + 'openapi.json'
export const OUT = ROOT + 'src/api.gen.ts'

const ident = (name) => (/^[A-Za-z_$][\w$]*$/.test(name) ? name : lit(name))
const lit = (v) => (typeof v === 'string' ? `'${v.replace(/\\/g, '\\\\').replace(/'/g, "\\'")}'` : JSON.stringify(v))
const group = (t) => (/[|&]/.test(t) ? `(${t})` : t)

/** 스키마 하나를 TypeScript 타입 글로 옮긴다 */
function type(s, pad) {
  if (s.$ref) return s.$ref.split('/').pop()
  if (s.anyOf) return [...new Set(s.anyOf.map((x) => type(x, pad)))].join(' | ')
  if ('const' in s) return lit(s.const)
  if (s.enum) return s.enum.map(lit).join(' | ')
  switch (s.type) {
    case 'string': return 'string'
    case 'integer': case 'number': return 'number'
    case 'boolean': return 'boolean'
    case 'null': return 'null'
    case 'array': return `${group(s.items ? type(s.items, pad) : 'unknown')}[]`
    case 'object': return object(s, pad)
    default: return 'unknown'
  }
}

function object(s, pad) {
  const extra = s.additionalProperties
  const rest = extra === true ? 'Record<string, unknown>'
    : extra && typeof extra === 'object' ? `Record<string, ${type(extra, pad)}>` : null
  if (!s.properties) return rest ?? 'Record<string, unknown>'
  const required = new Set(s.required ?? [])
  const inner = pad + '  '
  const lines = Object.entries(s.properties).map(([k, p]) =>
    `${p.description ? `${inner}/** ${p.description} */\n` : ''}${inner}${ident(k)}${required.has(k) ? '' : '?'}: ${type(p, inner)}`)
  const body = `{\n${lines.join('\n')}\n${pad}}`
  return rest ? `${body} & ${rest}` : body
}

export function generate(spec) {
  const out = ['// 만든 파일: 고치지 마세요. `npm run gen:api`로 다시 만듭니다 (scripts/gen-api-types.mjs).',
    `// 출처: 백엔드 응답 모델 → frontend/openapi.json (${spec.info.title} ${spec.info.version})`, '']
  for (const [name, s] of Object.entries(spec.components.schemas).sort(([a], [b]) => a.localeCompare(b))) {
    const doc = s.description ? `/** ${s.description.trim().replace(/\n+/g, ' ')} */\n` : ''
    out.push(`${doc}export type ${name} = ${type(s, '')}`, '')
  }
  return out.join('\n')
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  writeFileSync(OUT, generate(JSON.parse(readFileSync(SPEC, 'utf8'))))
  console.log('만듦:', OUT)
}
