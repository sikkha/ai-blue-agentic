import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react"
import { LockKeyholeIcon } from "lucide-react"

import App from "@/App"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { accountRequest, authFetch, SESSION_ENDED, setSession, type Account, type Session } from "@/lib/auth"

function message(error: unknown) {
  return error instanceof Error ? error.message : "Request failed."
}

export function AuthenticatedApp() {
  const [identity, setIdentity] = useState<Session | null>(null)
  const [loading, setLoading] = useState(true)
  const [notice, setNotice] = useState("")
  const [usersOpen, setUsersOpen] = useState(false)
  const [working, setWorking] = useState(false)

  const end = useCallback((detail = "") => {
    setSession(null)
    setIdentity(null)
    setUsersOpen(false)
    setNotice(detail)
    window.history.replaceState(null, "", window.location.pathname)
  }, [])

  useEffect(() => {
    let live = true
    void authFetch("/api/auth/session").then(async (response) => {
      if (response.status === 401) return
      if (!response.ok) throw new Error("Could not check your session. Try signing in again.")
      const current: Session = await response.json()
      if (live) {
        setSession(current)
        setIdentity(current)
      }
    }).catch((error) => {
      if (live) setNotice(message(error))
    }).finally(() => {
      if (live) setLoading(false)
    })
    const expired = () => end("Your session ended. Sign in again.")
    window.addEventListener(SESSION_ENDED, expired)
    return () => {
      live = false
      window.removeEventListener(SESSION_ENDED, expired)
    }
  }, [end])

  useEffect(() => {
    if (!identity) return
    const timeout = window.setTimeout(() => end("Your session expired. Sign in again."),
      Math.max(0, identity.expires_at * 1000 - Date.now()))
    return () => window.clearTimeout(timeout)
  }, [identity, end])

  async function login(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const fields = new FormData(form)
    setNotice("")
    setWorking(true)
    try {
      const current = await accountRequest<Session>("/api/auth/login", "POST", {
        username: fields.get("username"), password: fields.get("password"),
      })
      setSession(current)
      setIdentity(current)
    } catch (error) {
      setNotice(message(error))
    } finally {
      form.reset()
      setWorking(false)
    }
  }

  async function logout() {
    setWorking(true)
    setNotice("")
    try {
      await accountRequest<void>("/api/auth/logout", "POST")
      end()
    } catch (error) {
      setNotice(message(error))
    } finally {
      setWorking(false)
    }
  }

  if (loading) return <main className="grid min-h-svh place-items-center">Checking session…</main>
  if (!identity) return (
    <main className="grid min-h-svh place-items-center bg-muted/50 px-4 py-10">
      <section className="w-full max-w-sm rounded-xl border bg-card p-7 shadow-sm" aria-labelledby="login-title">
        <LockKeyholeIcon className="mb-5 size-7 text-primary" aria-hidden="true" />
        <h1 id="login-title" className="text-2xl font-semibold tracking-tight">Sign in to AI-Blue</h1>
        <form onSubmit={login} className="mt-6 grid gap-4">
          <label className="grid gap-2 text-sm font-medium">Username
            <Input name="username" autoComplete="username" maxLength={64} required />
          </label>
          <label className="grid gap-2 text-sm font-medium">Password
            <Input name="password" type="password" autoComplete="current-password" maxLength={128} required />
          </label>
          {notice && <p role="alert" className="text-sm text-destructive">{notice}</p>}
          <Button type="submit" disabled={working}>{working ? "Signing in…" : "Sign in"}</Button>
        </form>
      </section>
    </main>
  )

  const admin = identity.user.role === "ADMIN"
  const controls = <>
    {admin && <Button variant="ghost" size="sm" onClick={() => setUsersOpen(!usersOpen)}>{usersOpen ? "Workspace" : "Users"}</Button>}
    <Button variant="outline" size="sm" onClick={logout} disabled={working}>Sign out</Button>
    {notice && <span role="alert" className="text-sm text-destructive">{notice}</span>}
  </>
  if (admin && usersOpen) return <UserManagement controls={controls} currentId={identity.user.id} />
  return <App admin={admin} agentEnabled={identity.user.agent_enabled} accountControls={controls} />
}

function UserManagement({ controls, currentId }: { controls: ReactNode; currentId: number }) {
  const [users, setUsers] = useState<Account[]>([])
  const [error, setError] = useState("")
  const [pending, setPending] = useState(false)
  const [selected, setSelected] = useState<Account | null>(null)

  useEffect(() => {
    let live = true
    void accountRequest<Account[]>("/api/auth/users").then((accounts) => {
      if (live) setUsers(accounts)
    }).catch((failure) => { if (live) setError(message(failure)) })
    return () => { live = false }
  }, [])

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const fields = new FormData(form)
    const fieldsToSave = { role: fields.get("role"), agent_enabled: fields.has("agent_enabled") }
    setError("")
    setPending(true)
    try {
      const password = String(fields.get("password") ?? "")
      const account = selected
        ? await accountRequest<Account>(`/api/auth/users/${selected.id}`, "PATCH", {
          ...fieldsToSave, enabled: fields.has("enabled"), ...(password && { password }),
        })
        : await accountRequest<Account>("/api/auth/users", "POST", {
          ...fieldsToSave, username: fields.get("username"), password,
        })
      setUsers((old) => [...old.filter((user) => user.id !== account.id), account]
        .sort((a, b) => a.username.localeCompare(b.username)))
      setSelected(null)
      if (account.id === currentId) await authFetch("/api/auth/session")
    } catch (failure) {
      setError(message(failure))
    } finally {
      const passwordField = form.elements.namedItem("password")
      if (passwordField instanceof HTMLInputElement) passwordField.value = ""
      setPending(false)
    }
  }

  return (
    <main className="mx-auto max-w-5xl space-y-6 px-4 py-8">
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="mr-auto text-2xl font-semibold tracking-tight">User management</h1>
        {controls}
      </header>
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      <div className="grid gap-4 md:grid-cols-2">
        <section className="rounded-lg border p-4" aria-label="Accounts">
          <ul className="divide-y">
            {users.map((user) => <li key={user.id} className="flex items-center gap-3 py-3">
              <span className="mr-auto break-all">{user.username}<span className="block text-sm text-muted-foreground">{user.role} · {user.enabled ? "Enabled" : "Disabled"}</span></span>
              <Button variant="outline" size="sm" disabled={pending} onClick={() => setSelected(user)}>Edit</Button>
            </li>)}
          </ul>
        </section>
        <form key={selected?.id ?? "new"} onSubmit={save} className="grid gap-4 rounded-lg border p-4">
          <h2 className="font-semibold">{selected ? `Edit ${selected.username}` : "Create account"}</h2>
          {!selected && <label className="grid gap-2 text-sm">Username<Input name="username" autoComplete="off" minLength={3} maxLength={64} required /></label>}
          <label className="grid gap-2 text-sm">{selected ? "New password (optional)" : "Password"}
            <Input name="password" type="password" autoComplete="new-password" minLength={12} maxLength={128} required={!selected} />
          </label>
          <label className="grid gap-2 text-sm">Role
            <select name="role" defaultValue={selected?.role ?? "USER"} className="rounded-md border bg-background p-2">
              <option value="USER">User</option><option value="ADMIN">Administrator</option>
            </select>
          </label>
          {selected && <label className="flex items-center gap-2 text-sm"><input name="enabled" type="checkbox" defaultChecked={selected.enabled} /> Enabled</label>}
          <label className="flex items-center gap-2 text-sm"><input name="agent_enabled" type="checkbox" defaultChecked={selected?.agent_enabled} /> Enable chat, uploads and tool approvals</label>
          <div className="flex gap-2"><Button disabled={pending} type="submit">{selected ? "Save changes" : "Create account"}</Button>
            {selected && <Button variant="outline" disabled={pending} type="button" onClick={() => setSelected(null)}>Cancel</Button>}
          </div>
        </form>
      </div>
    </main>
  )
}
