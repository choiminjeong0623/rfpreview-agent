import { request, type FullConfig } from '@playwright/test'
import { PASSWORD } from './helpers'

// 로그인 (add-session-auth): 모든 시험은 기본 엔지니어로 로그인한 쿠키로 시작한다 (e2e/.auth, 커밋하지 않음).
// 다른 사용자는 시험 안에서 as()·asLogin()으로 바꾼다. 비밀번호는 E2E_PASSWORD (기본 demo-pass-1)
export const STATE = 'e2e/.auth/engineer.json'

export default async function globalSetup(config: FullConfig) {
  const baseURL = config.projects[0].use.baseURL
  const ctx = await request.newContext({ baseURL })
  const res = await ctx.post('/api/auth/login', { data: { login_id: 'engineer', password: PASSWORD } })
  if (res.status() !== 200) {
    throw new Error(`엔지니어 로그인 실패 ${res.status()}: ${await res.text()}\n`
      + '  비밀번호를 정하세요: cd backend && uv run rfp-db set-password --login engineer (E2E_PASSWORD와 같게)')
  }
  await ctx.storageState({ path: STATE })
  await ctx.dispose()
}
