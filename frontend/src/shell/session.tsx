import { useState, type ReactNode } from 'react'
import { api } from '../api'
import { useLoad } from '../components/useLoad'
import { SessionContext } from './useSession'

// 로그인 대신 머리글에서 고른 사용자 (_공통규칙.md 5장). 고른 사용자는 브라우저에 기억한다.

const KEY = 's2w.user'

function savedUserId(): number | null {
  try {
    const v = localStorage.getItem(KEY)
    return v ? Number(v) : null
  } catch {
    return null
  }
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const users = useLoad(() => api.users(), [])
  const [userId, setUserIdState] = useState<number | null>(savedUserId)
  const list = users.data ?? []
  const user = list.find((u) => u.user_id === userId) ?? list[0] ?? null
  const setUserId = (id: number) => {
    setUserIdState(id)
    try { localStorage.setItem(KEY, String(id)) } catch { /* 기억하지 못해도 화면은 동작한다 */ }
  }
  return (
    <SessionContext.Provider value={{ user, users: list, setUserId, usersError: users.error }}>
      {children}
    </SessionContext.Provider>
  )
}
