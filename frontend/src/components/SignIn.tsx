// Sign-in screen (ui.md §2.9): no sign-up, no password reset (demo users only).
import { type FormEvent, useState } from 'react'
import { useSignIn } from '../api/hooks'

export function SignIn() {
  const signIn = useSignIn()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')

  function submit(event: FormEvent) {
    event.preventDefault()
    signIn.mutate({ username, password })
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <form
        onSubmit={submit}
        className="w-full max-w-sm rounded-xl border border-grey-200 bg-white p-8 shadow-sm"
      >
        <h1 className="font-serif text-3xl">Member messages</h1>
        <p className="mt-1 text-grey-500">Sign in to review refund requests.</p>
        <label className="mt-8 block text-sm font-medium" htmlFor="username">
          Username
        </label>
        <input
          id="username"
          autoComplete="username"
          required
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          className="mt-1 w-full rounded-md border border-grey-300 px-3 py-2"
        />
        <label className="mt-4 block text-sm font-medium" htmlFor="password">
          Password
        </label>
        <input
          id="password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          className="mt-1 w-full rounded-md border border-grey-300 px-3 py-2"
        />
        {signIn.error && (
          <p role="alert" className="mt-4 text-sm text-error">
            {signIn.error.message}
          </p>
        )}
        <button
          type="submit"
          disabled={signIn.isPending}
          className="mt-6 w-full rounded-md bg-navy px-4 py-2.5 font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-60"
        >
          {signIn.isPending ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </main>
  )
}
