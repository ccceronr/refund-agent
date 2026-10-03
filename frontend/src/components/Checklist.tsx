// One line per rule check, icon plus sentence: status never by color alone (ui.md §1, §2.3).
import { Check as CheckIcon, TriangleAlert, X } from 'lucide-react'
import type { Check } from '../api/types'

export function Checklist({ checks }: { checks: Check[] }) {
  return (
    <ul className="mt-5 space-y-2">
      {checks.map((check) => (
        <li key={check.rule} className="flex gap-2.5">
          <CheckMark check={check} />
          <span>{check.text}</span>
        </li>
      ))}
    </ul>
  )
}

function CheckMark({ check }: { check: Check }) {
  if (!check.ok) {
    return (
      <>
        <X aria-hidden className="mt-1 size-4 shrink-0 text-error" />
        <span className="sr-only">Not met:</span>
      </>
    )
  }
  if (check.warning) {
    return (
      <>
        <TriangleAlert
          aria-hidden
          className="mt-1 size-4 shrink-0 text-warning"
        />
        <span className="sr-only">Note:</span>
      </>
    )
  }
  return (
    <>
      <CheckIcon aria-hidden className="mt-1 size-4 shrink-0 text-success" />
      <span className="sr-only">Met:</span>
    </>
  )
}
