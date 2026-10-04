import { describe, expect, it } from 'vitest'
import type { CaseDetail, Proposal } from '../api/types'
import { availableActions, type DraftState } from './actions'

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

const UNCHANGED: DraftState = {
  changed: false,
  outcome: 'refund',
  feeMissing: false,
}

// ui.md §2.7 and §4: which button for which tier, actor and edit state.
describe('availableActions', () => {
  it('lets staff approve a staff-tier proposal as it is', () => {
    expect(availableActions(caseWith('ready', {}), 'staff', UNCHANGED)).toEqual(
      {
        primary: { kind: 'approve', label: 'Approve and send', enabled: true },
        canReject: true,
      },
    )
  })

  it('switches to sending the edited reply once the text changes', () => {
    const edited = { ...UNCHANGED, changed: true }
    expect(
      availableActions(caseWith('ready', {}), 'staff', edited).primary,
    ).toEqual({
      kind: 'edit',
      label: 'Send edited reply',
      enabled: true,
    })
  })

  it('names the override when a supervisor turns a no-refund into a refund', () => {
    const detail = caseWith('ready', {
      recommendation: 'NO_REFUND',
      reason_code: 'LIMIT_REACHED',
    })
    const override = {
      changed: true,
      outcome: 'refund',
      feeMissing: false,
    } as const
    expect(
      availableActions(detail, 'supervisor', override).primary?.label,
    ).toBe('Refund and send')
  })

  it('makes staff wait for a supervisor on a supervisor-tier refund, even after editing', () => {
    const detail = caseWith('needs_supervisor', { tier: 'SUPERVISOR' })
    const edited = { ...UNCHANGED, changed: true }
    expect(availableActions(detail, 'staff', edited).primary).toEqual({
      kind: 'approve',
      label: 'Waiting for a supervisor',
      enabled: false,
    })
    expect(
      availableActions(detail, 'supervisor', UNCHANGED).primary?.enabled,
    ).toBe(true)
  })

  it('offers a reply on a manual case, and a refund only once the fee is picked', () => {
    const detail = caseWith('manual_review', {
      recommendation: 'MANUAL',
      tier: 'MANUAL',
    })
    const reply = {
      changed: false,
      outcome: 'no_refund',
      feeMissing: false,
    } as const
    const noFeeYet = {
      changed: true,
      outcome: 'refund',
      feeMissing: true,
    } as const

    expect(availableActions(detail, 'staff', reply)).toEqual({
      primary: { kind: 'edit', label: 'Send reply', enabled: true },
      canReject: false,
    })
    expect(availableActions(detail, 'staff', noFeeYet).primary).toEqual({
      kind: 'edit',
      label: 'Pick the fee first',
      enabled: false,
    })
  })

  it('offers nothing once the case is decided or before it is prepared', () => {
    expect(
      availableActions(caseWith('resolved', {}), 'staff', UNCHANGED).primary,
    ).toBeNull()
    expect(
      availableActions(caseWith('auto_resolved', {}), 'supervisor', UNCHANGED)
        .primary,
    ).toBeNull()
    expect(
      availableActions(caseWith('new', null), 'staff', UNCHANGED).primary,
    ).toBeNull()
  })
})
