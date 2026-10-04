// Which action the bar offers (ui.md §2.7). The server enforces BR-09 again on every
// decision; this only decides what to show.
import type { CaseDetail, Role } from '../api/types'
import type { Outcome } from './decision'

export interface PrimaryAction {
  kind: 'approve' | 'edit'
  label: string
  enabled: boolean
}

export interface Actions {
  primary: PrimaryAction | null
  canReject: boolean
}

export interface DraftState {
  changed: boolean // the reply or the outcome differs from the proposal
  outcome: Outcome
  feeMissing: boolean // refunding an ambiguous fee before picking one
}

const NO_ACTIONS: Actions = { primary: null, canReject: false }
const CLOSED = new Set(['resolved', 'auto_resolved', 'running'])

export function availableActions(
  detail: CaseDetail,
  role: Role,
  draft: DraftState,
): Actions {
  const proposal = detail.proposal
  if (!proposal || CLOSED.has(detail.status)) return NO_ACTIONS
  // Sent to a supervisor (ui.md §2.7): staff waits, as for a supervisor-tier refund.
  if (detail.status === 'needs_supervisor' && role !== 'supervisor') {
    return {
      primary: action('approve', 'Waiting for a supervisor', false),
      canReject: true,
    }
  }
  if (proposal.recommendation === 'MANUAL')
    return { primary: manualAction(draft), canReject: false }
  if (proposal.tier === 'SUPERVISOR' && role !== 'supervisor') {
    return {
      primary: action('approve', 'Waiting for a supervisor', false),
      canReject: true,
    }
  }
  if (!draft.changed)
    return { primary: action('approve', 'Approve and send'), canReject: true }
  const overridden =
    draft.outcome === 'refund' && proposal.recommendation === 'NO_REFUND'
  return {
    primary: action(
      'edit',
      overridden ? 'Refund and send' : 'Send edited reply',
    ),
    canReject: true,
  }
}

// "Ask a supervisor" (ui.md §2.7): staff only, on a case ready for them with a suggestion.
export function canAskSupervisor(detail: CaseDetail, role: Role): boolean {
  return (
    role === 'staff' && detail.status === 'ready' && detail.proposal !== null
  )
}

function manualAction(draft: DraftState): PrimaryAction {
  if (draft.outcome === 'no_refund') return action('edit', 'Send reply')
  if (draft.feeMissing) return action('edit', 'Pick the fee first', false)
  return action('edit', 'Refund and send')
}

function action(
  kind: PrimaryAction['kind'],
  label: string,
  enabled = true,
): PrimaryAction {
  return { kind, label, enabled }
}
