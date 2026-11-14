import { createContext, useContext } from 'react'
import type { User } from '../api'

export type Session = { user: User | null; users: User[]; setUserId: (id: number) => void; usersError: string | null }

export const SessionContext = createContext<Session>({ user: null, users: [], setUserId: () => undefined, usersError: null })

/** 머리글에서 고른 사용자 (SessionProvider). */
export function useSession(): Session {
  return useContext(SessionContext)
}
