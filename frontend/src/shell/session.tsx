import { useState, type ReactNode } from 'react'
import { api } from '../api'
import { useLoad } from '../components/useLoad'
import { SessionContext } from './useSession'

// 로그인한 사용자 (add-session-auth). 세션은 서버가 쿠키(HttpOnly)로 들고, 화면은 /auth/me로 누구인지만 안다.
// 브라우저에 사용자를 따로 기억하지 않는다. 세션이 없으면 API가 401을 주고 api.ts가 로그인 화면으로 보낸다.

export function SessionProvider({ children }: { children: ReactNode }) {
  const [version, setVersion] = useState(0)
  const me = useLoad(() => api.me(), [version])
  const user = me.data
  // 결재자·담당자를 고르는 목록 (로그인한 뒤에만)
  const users = useLoad(() => (user ? api.users() : Promise.resolve([])), [user?.user_id])
  const refresh = () => setVersion((v) => v + 1)
  // 로그아웃: 서버 세션을 끝낸다. 실패해도 쿠키 없는 상태와 같게 다시 읽는다
  const signOut = async () => {
    try { await api.logout() } catch { /* 이미 끝난 세션이어도 로그인 화면으로 간다 */ }
    refresh()
  }
  return (
    <SessionContext.Provider value={{ user: user ?? null, users: users.data ?? [], refresh, signOut, usersError: users.error }}>
      {children}
    </SessionContext.Provider>
  )
}
