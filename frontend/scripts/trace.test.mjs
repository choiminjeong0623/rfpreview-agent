// 추적표 만들기·목업 배치 점검 테스트 (change add-spec-trace, 명세 spec-verification). 실행: npm run test:trace
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { compareAreas } from './compare-mockup.mjs'
import { build, load, parseE2eTests, parsePyTests, stale } from './trace.mjs'

/** 작은 저장소 하나: FR 2개, capability 2개, 화면 1개 */
function input(over = {}) {
  const tests = [
    ...parsePyTests('def test_a(db):\n    """Scenario: 첫 시나리오 / 둘째 시나리오 — 설명."""\n', 'backend/tests/test_a.py'),
    ...parseE2eTests("// Scenario: 화면 시나리오\ntest('화면 기준', async () => {})\n", 'frontend/e2e/a.spec.ts'),
  ]
  return {
    config: {
      fr: { 'FR-01': { specs: ['cap-a'] }, 'FR-02': { specs: ['cap-b'] } },
      common: {},
      screens: { 'SCR-01': { fr: ['FR-02'], components: ['views/A.tsx'] } },
      flows: {},
    },
    frs: [{ id: 'FR-01', name: '하나', priority: 'Must' }, { id: 'FR-02', name: '둘', priority: 'Must' }],
    specs: { 'cap-a': ['첫 시나리오', '둘째 시나리오'], 'cap-b': ['화면 시나리오', '테스트 없는 것'] },
    tests,
    screens: { 'SCR-01': { file: 'docs/screens/SCR-01-a.md', title: 'a', criteria: [{ name: '화면 기준', text: '…' }] } },
    exists: () => true,
    ...over,
  }
}

test('Scenario: 이름으로 테스트 잇기', () => {
  const { text, errors, stats } = build(input())
  assert.deepEqual(errors, [])
  assert.match(text, /\| 첫 시나리오 \| `tests\/test_a\.py:1` \|/)
  assert.match(text, /\| 화면 시나리오 \| `e2e\/a\.spec\.ts:2` \|/)
  assert.equal(stats.doneSc, 3)
  assert.equal(stats.doneAc, 1)
})

test('Scenario: 테스트 없는 시나리오', () => {
  const { text } = build(input())
  const unverified = text.split('## 5. 검증 안 된 것')[1]
  assert.match(unverified, /\| `cap-b` \| 테스트 없는 것 \|/)
  assert.doesNotMatch(unverified, /첫 시나리오/)
})

test('Scenario: 같은 입력 같은 표', () => {
  assert.equal(build(input()).text, build(input()).text)
  assert.equal(build(load()).text, build(load()).text)          // 저장소 전체로도
})

test('Scenario: 낡은 추적표', () => {
  const before = build(input()).text
  const renamed = input()
  renamed.tests = renamed.tests.map((t) => (t.name === '첫 시나리오' ? { ...t, name: '바뀐 이름' } : t))
  const after = build(renamed).text
  assert.match(stale(before, after), /npm run trace/)
  assert.equal(stale(after, after), null)
})

test('Scenario: 없는 컴포넌트 파일', () => {
  const { errors } = build(input({ exists: (p) => p !== 'views/A.tsx' }))
  assert.ok(errors.some((e) => e.includes('frontend/src/views/A.tsx')), errors.join('\n'))
})

test('설정에 없는 capability·이어진 것이 없는 FR은 실패', () => {
  const extra = input()
  extra.specs = { ...extra.specs, 'cap-c': ['홀로'] }
  extra.frs = [...extra.frs, { id: 'FR-03', name: '셋', priority: 'Should' }]
  extra.config.fr['FR-03'] = { specs: [] }
  const { errors } = build(extra)
  assert.ok(errors.some((e) => e.includes('"cap-c"가 설정')))
  assert.ok(errors.some((e) => e.includes('FR-03에 이어진')))
})

test('docstring 여러 줄의 Scenario와 줄 끝 —', () => {
  const t = parsePyTests('def test_b():\n    """Scenario: 가 ·\n    Scenario: 나 / 다 —\n    설명."""\n', 'x.py').map((x) => x.name)
  assert.deepEqual(t, ['가', '나', '다'])
})

test('Scenario: 배치 같음', () => {
  const r = compareAreas(['ttl', 'qsum', 'tbl'], ['ttl', 'extra', 'qsum', 'tbl'])
  assert.equal(r.ok, true)
  assert.deepEqual(r.extra, ['extra'])
})

test('Scenario: 영역이 빠짐', () => {
  const r = compareAreas(['ttl', 'ais', 'tbl'], ['tbl', 'ttl'])
  assert.deepEqual(r.missing, ['ais'])
  assert.equal(r.sameOrder, false)
  assert.equal(r.ok, false)
})
