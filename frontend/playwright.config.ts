import { defineConfig } from '@playwright/test'

// 화면 E2E. 백엔드(8000)와 `npm run dev`(5173)를 먼저 띄운다. CI(.github/workflows/ci.yml e2e)는
// 합성 문서만으로 돌리고, RFP 원문(data/private/rfp_docx)이 있어야 하는 테스트는 스스로 건너뛴다.
export default defineConfig({
  testDir: 'e2e',
  timeout: 300_000,
  expect: { timeout: 30_000 },
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:5173',
    screenshot: 'only-on-failure',
    launchOptions: process.env.PW_CHROMIUM ? { executablePath: process.env.PW_CHROMIUM } : {},
  },
})
