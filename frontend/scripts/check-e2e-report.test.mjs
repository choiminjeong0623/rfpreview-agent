// e2e 결과 검사 도구 테스트 (add-e2e-ci). 실행: node --test scripts/check-e2e-report.test.mjs
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { problems } from './check-e2e-report.mjs'

test('Scenario: 건너뛴 e2e는 실패', () => {
  assert.deepEqual(problems({ expected: 1, skipped: 1, unexpected: 0, flaky: 0 }),
    ['건너뛴 시험 1개 (준비가 빠졌는지 보세요)'])
  assert.deepEqual(problems({ expected: 0, skipped: 0, unexpected: 0, flaky: 0 }), ['돈 시험이 0개입니다'])
})

test('모두 통과면 문제 없음, 실패는 실패', () => {
  assert.deepEqual(problems({ expected: 6, skipped: 0, unexpected: 0, flaky: 0 }), [])
  assert.deepEqual(problems({ expected: 5, skipped: 0, unexpected: 1, flaky: 0 }), ['실패 1개'])
})
