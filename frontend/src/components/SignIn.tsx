// Sign-in screen (ui.md §2.9): no sign-up, no password reset (demo users only).
import { CircleAlert, Eye, EyeOff, LoaderCircle } from 'lucide-react'
import { type FormEvent, useState } from 'react'
import { useSignIn } from '../api/hooks'
import { ProductMark } from './Brand'

export function SignIn() {
  const signIn = useSignIn()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)

  function submit(event: FormEvent) {
    event.preventDefault()
    signIn.mutate({ username, password })
  }

  return (
    <main className="flex min-h-dvh items-center justify-center px-4 py-10">
      <form onSubmit={submit} className="card w-full max-w-sm p-6 sm:p-8">
        <ProductMark />
        <h1 className="mt-6 text-[1.75rem] leading-tight font-medium tracking-tight">
          Member messages
        </h1>
        <p className="mt-1 text-grey-600">Sign in to review refund requests.</p>
        <label className="mt-8 block text-sm font-medium" htmlFor="username">
          Username
        </label>
        <input
          id="username"
          autoComplete="username"
          autoFocus
          required
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          className="field mt-1.5 h-11"
        />
        <label className="mt-4 block text-sm font-medium" htmlFor="password">
          Password
        </label>
        <div className="relative mt-1.5">
          <input
            id="password"
            type={showPassword ? 'text' : 'password'}
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="field h-11 pr-11"
          />
          <button
            type="button"
            onClick={() => setShowPassword((shown) => !shown)}
            aria-label={showPassword ? 'Hide password' : 'Show password'}
            aria-pressed={showPassword}
            className="button-quiet absolute top-0.5 right-0.5 size-10 px-0"
          >
            {showPassword ? (
              <EyeOff aria-hidden className="size-4" />
            ) : (
              <Eye aria-hidden className="size-4" />
            )}
          </button>
        </div>
        {signIn.error && (
          <p
            role="alert"
            className="mt-4 flex items-start gap-2 rounded-xl bg-error/8 px-3 py-2 text-sm text-error"
          >
            <CircleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
            {signIn.error.message}
          </p>
        )}
        <button
          type="submit"
          disabled={signIn.isPending}
          className="button-primary mt-6 h-11 w-full disabled:cursor-wait"
        >
          {signIn.isPending && (
            <LoaderCircle aria-hidden className="size-4 animate-spin" />
          )}
          {signIn.isPending ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </main>
  )
}
