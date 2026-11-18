export type Account = {
  id: number
  username: string
  role: "ADMIN" | "USER"
  enabled: boolean
  agent_enabled: boolean
}

export type Session = { user: Account; csrf: string; expires_at: number }

let session: Session | null = null
export const SESSION_ENDED = "aiblue:session-ended"

export function setSession(value: Session | null) {
  session = value
}

export async function authFetch(url: string, init?: RequestInit) {
  const current = session
  const headers = new Headers(init?.headers)
  if (current) headers.set("X-CSRF-Token", current.csrf)
  const response = await fetch(url, { ...init, headers, credentials: "same-origin" })
  if (response.status === 401 && url !== "/api/auth/login" && current && current === session) {
    window.dispatchEvent(new Event(SESSION_ENDED))
  }
  return response
}

export async function accountRequest<T>(url: string, method = "GET", body?: unknown): Promise<T> {
  const response = await authFetch(url, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    throw new Error(typeof data.detail === "string" ? data.detail : `Request failed (${response.status}).`)
  }
  return response.status === 204 ? (undefined as T) : response.json()
}
