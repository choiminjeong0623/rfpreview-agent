import { defineConfig } from '@playwright/test'

// 화면 E2E. 백엔드(8000)와 `npm run dev`(5173)를 먼저 띄운다. CI(.github/workflows/ci.yml e2e)는
// 합성 문서만으로 돌리고, RFP 원문(data/private/rfp_docx)이 있어야 하는 테스트는 스스로 건너뛴다.
export default defineConfig({
  testDir: 'e2e',
  // 기본 엔지니어로 로그인한 쿠키를 저장해 두고 모든 시험이 쓴다 (add-session-auth)
  globalSetup: './e2e/global-setup.ts',
  timeout: 300_000,
  expect: { timeout: 30_000 },
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:5173',
    storageState: 'e2e/.auth/engineer.json',
    screenshot: 'only-on-failure',
    launchOptions: process.env.PW_CHROMIUM ? { executablePath: process.env.PW_CHROMIUM } : {},
  },
})
