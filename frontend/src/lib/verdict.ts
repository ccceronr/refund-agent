// The kind of outcome the recommendation card shows at a glance (ui.md §2.3). The headline
// still says it in words: the tone only picks the icon and the color of the band.
import type { CaseStatus, Recommendation } from '../api/types'

export type VerdictTone = 'refund' | 'no_refund' | 'review' | 'other'

const TONE_BY_RECOMMENDATION: Record<Recommendation, VerdictTone> = {
  REFUND: 'refund',
  NO_REFUND: 'no_refund',
  MANUAL: 'review',
}

export function verdictTone(
  status: CaseStatus,
  recommendation: Recommendation,
): VerdictTone {
  if (status === 'not_refund') return 'other'
  return TONE_BY_RECOMMENDATION[recommendation]
}
