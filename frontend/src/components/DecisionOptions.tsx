// What to do when it isn't simply "approve" (ui.md §2.6): refund or not, and on an
// AMBIGUOUS_FEE case, which fee, picked by date and amount, never by id.
import type { FeeChoice } from '../api/types'
import type { DecisionChoices, Outcome } from '../lib/decision'

interface DecisionOptionsProps {
  choices: DecisionChoices
  feeChoices: FeeChoice[]
  outcome: Outcome
  feeId: number | null
  onOutcome: (outcome: Outcome) => void
  onFee: (feeId: number) => void
}

export function DecisionOptions(props: DecisionOptionsProps) {
  const { choices, feeChoices, outcome, feeId, onOutcome, onFee } = props
  if (choices.outcomes.length === 0) return null
  return (
    <fieldset className="space-y-3">
      <legend className="label">Your decision</legend>
      <div className="grid grid-cols-2 gap-2">
        {choices.outcomes.map((option) => (
          <label
            key={option.outcome}
            className={`flex min-h-10 cursor-pointer items-center gap-2.5 rounded-xl border bg-white px-3.5 py-2 transition-colors duration-150 hover:border-grey-400 has-checked:border-navy has-checked:ring-1 has-checked:ring-navy has-focus-visible:outline-2 has-focus-visible:outline-terracotta has-disabled:cursor-not-allowed has-disabled:bg-grey-50 has-disabled:text-grey-600 ${
              option.outcome === outcome ? 'border-navy' : 'border-grey-300'
            }`}
          >
            <input
              type="radio"
              name="outcome"
              value={option.outcome}
              checked={option.outcome === outcome}
              disabled={!option.enabled}
              onChange={() => onOutcome(option.outcome)}
              className="accent-navy"
            />
            {option.label}
          </label>
        ))}
      </div>
      {choices.outcomes.map(
        (option) =>
          option.hint && (
            <p key={option.outcome} className="text-sm text-grey-600">
              {option.hint}
            </p>
          ),
      )}
      {choices.needsFeePick && outcome === 'refund' && (
        <div>
          <p className="text-sm font-medium text-grey-700">Which fee?</p>
          <div className="mt-1.5 flex flex-col gap-1.5">
            {feeChoices.map((fee) => (
              <label
                key={fee.id}
                className="flex min-h-10 cursor-pointer items-center gap-2.5 rounded-xl border border-grey-300 bg-white px-3.5 transition-colors duration-150 hover:border-grey-400 has-checked:border-navy has-checked:ring-1 has-checked:ring-navy has-focus-visible:outline-2 has-focus-visible:outline-terracotta"
              >
                <input
                  type="radio"
                  name="fee"
                  checked={fee.id === feeId}
                  onChange={() => onFee(fee.id)}
                  className="accent-navy"
                />
                {fee.label}
              </label>
            ))}
          </div>
        </div>
      )}
    </fieldset>
  )
}
