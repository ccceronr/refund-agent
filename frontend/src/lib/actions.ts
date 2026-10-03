// Which action the bar offers (ui.md §2.7). The server enforces BR-09 again on every
// decision; this only decides what to show.
import type { CaseDetail, Role } from '../api/types'

export interface PrimaryAction {
  kind: 'approve' | 'edit'
  label: string
  enabled: boolean
}

export interface Actions {
  primary: PrimaryAction | null
  canReject: boolean
}

const DECIDED = new Set(['resolved', 'auto_resolved', 'running'])

export function availableActions(
  detail: CaseDetail,
  role: Role,
  edited: boolean,
): Actions {
  const proposal = detail.proposal
  if (!proposal || DECIDED.has(detail.status))
    return { primary: null, canReject: false }
  if (proposal.recommendation === 'MANUAL') {
    return {
      primary: { kind: 'edit', label: 'Send reply', enabled: true },
      canReject: false,
    }
  }
  if (edited) {
    return {
      primary: { kind: 'edit', label: 'Send edited reply', enabled: true },
      canReject: true,
    }
  }
  if (proposal.tier === 'SUPERVISOR' && role !== 'supervisor') {
    const waiting = {
      kind: 'approve',
      label: 'Waiting for a supervisor',
      enabled: false,
    } as const
    return { primary: waiting, canReject: true }
  }
  return {
    primary: { kind: 'approve', label: 'Approve and send', enabled: true },
    canReject: true,
  }
}
