import { useMemo, useState, type ReactNode } from 'react'
import { apiRequest, setAccessToken, type AuthResponse, type UserRole } from '../api'
import { AuthContext, type AuthState } from './AuthStore'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [role, setRole] = useState<UserRole | null>(null)
  const [userId, setUserId] = useState<number | null>(null)

  const value = useMemo<AuthState>(
    () => ({
      role,
      userId,
      requestOtp: async (phone) => {
        await apiRequest<{ message: string }>('/auth/request-otp', {
          method: 'POST',
          body: JSON.stringify({ phone }),
        })
      },
      signIn: async (phone, otp) => {
        const result = await apiRequest<AuthResponse>('/auth/verify-otp', {
          method: 'POST',
          body: JSON.stringify({ phone, otp }),
        })
        setAccessToken(result.access_token)
        setRole(result.role)
        setUserId(result.user_id)
      },
      signOut: () => {
        setAccessToken(null)
        setRole(null)
        setUserId(null)
      },
    }),
    [role, userId],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

