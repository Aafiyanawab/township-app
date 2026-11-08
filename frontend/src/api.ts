export type UserRole = 'resident' | 'helpdesk' | 'accounts' | 'committee'

export type AuthResponse = {
  access_token: string
  token_type: 'bearer'
  user_id: number
  role: UserRole
}

export type Bill = {
  id: number
  period: string
  amount: string
  paid_amount: string
  outstanding: string
  late_fee: string
  days_overdue: number
  due_on: string
}

export type LedgerEntry = {
  id: number
  kind: string
  amount: string
  note: string | null
  entry_date: string
  bill_id: number | null
  payment_id: number | null
}

export type ComplaintEvent = {
  id: number
  kind: string
  detail: string | null
  at: string
}

export type Complaint = {
  id: number
  text: string
  status: string
  category: string
  urgency: string
  created_at: string
  respond_by: string | null
  events: ComplaintEvent[]
}

export type PaymentReceipt = {
  payment_id: number
  bill_id: number
  amount: string
}

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

let accessToken: string | null = null

export function setAccessToken(token: string | null) {
  accessToken = token
}

const apiBaseUrl = (import.meta.env.VITE_API_URL ?? '').replace(/\/$/, '')

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set('Accept', 'application/json')
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`)
  if (init.body && !(init.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  let response: Response
  try {
    response = await fetch(`${apiBaseUrl}${path}`, { ...init, headers })
  } catch {
    throw new ApiError('Could not connect. Check your connection and try again.', 0)
  }

  const contentType = response.headers.get('content-type') ?? ''
  const payload: unknown = contentType.includes('application/json')
    ? await response.json()
    : await response.text()

  if (!response.ok) {
    const detail =
      typeof payload === 'object' && payload !== null && 'detail' in payload
        ? payload.detail
        : undefined
    const message = Array.isArray(detail)
      ? detail.map((item: unknown) => {
          if (typeof item === 'object' && item !== null && 'msg' in item) return String(item.msg)
          return String(item)
        }).join(', ')
      : typeof detail === 'string'
        ? detail
        : 'Something went wrong. Please try again.'
    throw new ApiError(message, response.status)
  }

  return payload as T
}

export function postJson<T>(path: string, body: unknown) {
  return apiRequest<T>(path, { method: 'POST', body: JSON.stringify(body) })
}
