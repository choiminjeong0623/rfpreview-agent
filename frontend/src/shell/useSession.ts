import { createContext, useContext } from 'react'
import type { SessionUser, User } from '../api'

export type Session = {
  user: SessionUser | null
  users: User[]
  /** 로그인한 뒤 사용자 다시 읽기 */
  refresh: () => void
  signOut: () => Promise<void>
  usersError: string | null
}

export const SessionContext = createContext<Session>({
  user: null, users: [], refresh: () => undefined, signOut: async () => undefined, usersError: null,
})

/** 로그인한 사용자 (SessionProvider, add-session-auth). */
export function useSession(): Session {
  return useContext(SessionContext)
}
