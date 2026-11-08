import { createContext } from 'react'
import type { UserRole } from '../api'

export type AuthState = {
  role: UserRole | null
  userId: number | null
  requestOtp: (phone: string) => Promise<void>
  signIn: (phone: string, otp: string) => Promise<void>
  signOut: () => void
}

export const AuthContext = createContext<AuthState | null>(null)
