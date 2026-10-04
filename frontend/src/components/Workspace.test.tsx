// @vitest-environment jsdom
// The policy panel closes cleanly with the X and with Esc, and approving still works
// afterwards (P7b bug: newer browsers return a Promise from scrollIntoView, and an effect
// that returned it crashed the whole page when the panel closed).
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type {
  CaseDetail,
  CaseListItem,
  PolicyDocument,
  Staff,
} from '../api/types'
import { ErrorBoundary } from './ErrorBoundary'
import { Workspace } from './Workspace'

const LUIS: Staff = { name: 'Luis', role: 'staff' }
const QUEUE: CaseListItem[] = [
  {
    id: 5012,
    member_name: 'Ana Ruiz',
    topic: 'Overdraft fee refund',
    status: 'ready',
    status_label: 'Ready for you',
    received_at: '2026-09-15T08:12:44',
    tier: 'STAFF',
  },
]
const CASE: CaseDetail = {
  id: 5012,
  status: 'ready',
  status_label: 'Ready for you',
  topic: 'Overdraft fee refund',
  received_at: '2026-09-15T08:12:44',
  member: {
    name: 'Ana Ruiz',
    standing: 'good',
    credit_union: 'Riverbend Credit Union',
  },
  messages: [
    {
      from: 'member',
      author_name: 'Ana',
      body: 'Can you refund this?',
      sent_at: '2026-09-15T08:12:44',
    },
  ],
  proposal: {
    recommendation: 'REFUND',
    reason_code: 'ELIGIBLE',
    tier: 'STAFF',
    headline: 'Refund the $35.00 overdraft fee',
    authority_note: 'You can approve this.',
    amount: '35.00',
    checks: [
      {
        rule: 'BR-02',
        ok: true,
        text: 'The paycheck arrived the same day.',
        warning: false,
      },
    ],
    policy_quote: {
      document: 'Fee Refund Policy',
      text: 'An overdraft fee qualifies…',
      slug: 'fee-refund-policy',
      passage_id: 3,
    },
    draft_reply: 'Hi Ana,\n\nWe have refunded the fee.',
    draft_source: 'writer',
    language: 'en',
    manual_reason: null,
    fee_choices: [],
  },
  evidence: null,
  run: { status: 'completed', duration_ms: 3000, cost_usd: '0.004', steps: [] },
  decision: null,
}
const POLICY: PolicyDocument = {
  slug: 'fee-refund-policy',
  title: 'Fee Refund Policy',
  passages: [
    {
      id: 2,
      text: 'Members in good standing may receive up to 3 fee refunds.',
    },
    { id: 3, text: 'An overdraft fee qualifies for a refund when…' },
  ],
}
const DECIDED = {
  status: 'resolved',
  status_label: 'Done',
  action: 'approve',
  outcome: 'refund',
  refunded: true,
  amount: '35.00',
}

function answer(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

const fetchMock = vi.fn(
  async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.endsWith('/decision') && init?.method === 'POST')
      return answer(DECIDED)
    if (url.endsWith('/api/cases')) return answer(QUEUE)
    if (url.endsWith('/api/cases/5012')) return answer(CASE)
    if (url.endsWith('/api/policies/fee-refund-policy')) return answer(POLICY)
    return new Response(null, { status: 404 })
  },
)

function renderWorkspace() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <ErrorBoundary>
        <Workspace staff={LUIS} />
      </ErrorBoundary>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
  // As in newer browsers ("scroll promises"): scrollIntoView returns a Promise.
  Element.prototype.scrollIntoView = () => Promise.resolve() as unknown as void
  window.history.pushState(null, '', '/?case=5012')
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  fetchMock.mockClear()
})

describe('the policy panel', () => {
  it('closes with the X, closes with Esc, and the case can still be approved', async () => {
    const user = userEvent.setup()
    renderWorkspace()
    const policyLink = await screen.findByRole('button', {
      name: 'Fee Refund Policy',
    })

    await user.click(policyLink)
    expect(
      await screen.findByRole('complementary', { name: 'Fee Refund Policy' }),
    ).toBeTruthy()
    await user.click(screen.getByRole('button', { name: 'Close' }))
    await waitFor(() => expect(screen.queryByRole('complementary')).toBeNull())
    expect(document.activeElement).toBe(policyLink)

    await user.click(policyLink)
    await screen.findByRole('complementary', { name: 'Fee Refund Policy' })
    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('complementary')).toBeNull())

    await user.click(screen.getByRole('button', { name: 'Approve and send' }))
    expect(await screen.findByText('Refunded and sent')).toBeTruthy()
    expect(
      screen.queryByText('Something went wrong. Reload the page.'),
    ).toBeNull()
  })

  it('pushes the case aside instead of covering it', async () => {
    const user = userEvent.setup()
    renderWorkspace()

    await user.click(
      await screen.findByRole('button', { name: 'Fee Refund Policy' }),
    )

    const panel = await screen.findByRole('complementary', {
      name: 'Fee Refund Policy',
    })
    const caseColumn = screen.getByRole('main')
    expect(panel.parentElement).toBe(caseColumn.parentElement) // a column of the same grid
    expect(panel.className).not.toMatch(/\bfixed\b/)
  })
})
