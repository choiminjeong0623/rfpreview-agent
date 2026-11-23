// CI e2e 결과 검사 (add-e2e-ci, 명세 spec-verification "핵심 흐름 e2e").
// Playwright JSON 결과(PLAYWRIGHT_JSON_OUTPUT_NAME)를 읽어, 실패·예상 밖 결과·건너뛴 시험이 있거나
// 돈 시험이 하나도 없으면 실패한다. 준비가 빠져 test.skip한 것을 "통과"로 보지 않기 위해서다.
// 실행: node scripts/check-e2e-report.mjs e2e-results.json
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

/** 결과 stats로 문제 목록을 만든다. 비면 통과. */
export function problems(stats) {
  const s = { expected: 0, skipped: 0, unexpected: 0, flaky: 0, ...stats }
  const out = []
  if (s.unexpected > 0) out.push(`실패 ${s.unexpected}개`)
  if (s.flaky > 0) out.push(`다시 돌려 통과한 시험 ${s.flaky}개 (흔들림)`)
  if (s.skipped > 0) out.push(`건너뛴 시험 ${s.skipped}개 (준비가 빠졌는지 보세요)`)
  if (s.expected === 0) out.push('돈 시험이 0개입니다')
  return out
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const path = process.argv[2] ?? 'e2e-results.json'
  const { stats } = JSON.parse(readFileSync(path, 'utf8'))
  const found = problems(stats)
  if (found.length) {
    console.error(`e2e 결과 검사 실패: ${found.join(', ')}`)
    process.exit(1)
  }
  console.log(`e2e 결과 검사 통과: 시험 ${stats.expected}개, 건너뜀 0`)
}
