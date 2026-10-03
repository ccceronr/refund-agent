import { describe, expect, it } from 'vitest'
import type { CaseDetail, Proposal } from '../api/types'
import { availableActions } from './actions'

function caseWith(
  status: CaseDetail['status'],
  proposal: Partial<Proposal> | null,
): CaseDetail {
  return {
    id: 5012,
    status,
    status_label: '',
    topic: '',
    received_at: '2026-09-15T08:12:44',
    member: { name: 'Ana Ruiz', standing: 'good', credit_union: '' },
    messages: [],
    proposal: proposal && {
      recommendation: 'REFUND',
      reason_code: 'ELIGIBLE',
      tier: 'STAFF',
      headline: '',
      authority_note: null,
      amount: '35.00',
      checks: [],
      policy_quote: null,
      draft_reply: 'Hi Ana',
      draft_source: 'writer',
      language: 'en',
      manual_reason: null,
      fee_choices: [],
      ...proposal,
    },
    evidence: null,
    run: null,
    decision: null,
  }
}

// ui.md §2.7 and §4: which button for which tier, actor and edit state.
describe('availableActions', () => {
  it('lets staff approve a staff-tier proposal as it is', () => {
    expect(availableActions(caseWith('ready', {}), 'staff', false)).toEqual({
      primary: { kind: 'approve', label: 'Approve and send', enabled: true },
      canReject: true,
    })
  })

  it('switches to sending the edited reply once the text changes', () => {
    expect(
      availableActions(caseWith('ready', {}), 'staff', true).primary,
    ).toEqual({
      kind: 'edit',
      label: 'Send edited reply',
      enabled: true,
    })
  })

  it('makes staff wait for a supervisor on a supervisor-tier refund', () => {
    const detail = caseWith('needs_supervisor', { tier: 'SUPERVISOR' })
    expect(availableActions(detail, 'staff', false).primary).toEqual({
      kind: 'approve',
      label: 'Waiting for a supervisor',
      enabled: false,
    })
    expect(availableActions(detail, 'supervisor', false).primary?.enabled).toBe(
      true,
    )
  })

  it('offers only a reply on a manual case', () => {
    const detail = caseWith('manual_review', {
      recommendation: 'MANUAL',
      tier: 'MANUAL',
    })
    expect(availableActions(detail, 'staff', false)).toEqual({
      primary: { kind: 'edit', label: 'Send reply', enabled: true },
      canReject: false,
    })
  })

  it('offers nothing once the case is decided or before it is prepared', () => {
    expect(
      availableActions(caseWith('resolved', {}), 'staff', false).primary,
    ).toBeNull()
    expect(
      availableActions(caseWith('auto_resolved', {}), 'supervisor', false)
        .primary,
    ).toBeNull()
    expect(
      availableActions(caseWith('new', null), 'staff', false).primary,
    ).toBeNull()
  })
})
