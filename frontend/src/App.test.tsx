// @vitest-environment jsdom
// Signing out goes back to the sign-in screen (ui.md §4: "logout clears session").
// Bug found in P7c: clearing the whole query cache detached the screen from the "who am I"
// answer, so the page stayed on the workspace after a successful sign-out.
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

function answer(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
  const url = String(input)
  if (url.endsWith('/api/auth/me'))
    return answer({ name: 'Luis', role: 'staff' })
  if (url.endsWith('/api/auth/logout'))
    return new Response(null, { status: 204 })
  if (url.endsWith('/api/cases')) return answer([])
  return new Response(null, { status: 404 })
})

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
  window.history.pushState(null, '', '/')
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  fetchMock.mockClear()
})

describe('signing out', () => {
  it('shows the sign-in screen again', async () => {
    const user = userEvent.setup()
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    render(
      <QueryClientProvider client={client}>
        <App />
      </QueryClientProvider>,
    )

    await user.click(await screen.findByRole('button', { name: 'Sign out' }))

    expect(await screen.findByLabelText('Username')).toBeTruthy()
  })
})
