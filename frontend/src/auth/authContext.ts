import { createContext } from 'react'
import type { User } from '../api/types'

export type AuthStatus = 'checking' | 'authenticated' | 'anonymous' | 'error'

export interface AuthContextValue {
  status: AuthStatus
  user: User | null
  /** Set when the initial session check fails for a non-auth reason. */
  error: string | null
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  /** Retry the initial GET /api/auth/me check. */
  retrySession: () => void
}

export const AuthContext = createContext<AuthContextValue | null>(null)
