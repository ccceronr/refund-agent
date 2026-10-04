// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ErrorBoundary } from './ErrorBoundary'

function Broken(): never {
  throw new TypeError('Ana Ruiz ••4210 broke it')
}

afterEach(cleanup)

describe('ErrorBoundary', () => {
  it('shows a plain message with a reload button instead of a blank page (A10)', () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined)

    render(
      <ErrorBoundary>
        <Broken />
      </ErrorBoundary>,
    )

    expect(
      screen.getByText('Something went wrong. Reload the page.'),
    ).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Reload' })).toBeTruthy()
  })

  it('logs the error type and where it happened, never its message', () => {
    const logged = vi
      .spyOn(console, 'error')
      .mockImplementation(() => undefined)

    render(
      <ErrorBoundary>
        <Broken />
      </ErrorBoundary>,
    )

    const ours = logged.mock.calls.find((call) => call[0] === 'render_failed')
    expect(ours?.[1]).toMatchObject({ error: 'TypeError' })
    expect(JSON.stringify(ours)).not.toContain('Ana')
    expect(JSON.stringify(ours)).not.toContain('4210')
  })
})
