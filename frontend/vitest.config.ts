import { defineConfig } from 'vitest/config'

// 화면 단위 테스트 (Vitest). 화면 계산 로직(src/**/*.test.ts)만 돌린다.
// e2e/*.spec.ts는 Playwright가 돌리므로 넣지 않는다.
export default defineConfig({
  test: { include: ['src/**/*.test.ts'], environment: 'node' },
})
