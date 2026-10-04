// One line per rule check, icon plus sentence: status never by color alone (ui.md §1, §2.3).
import { Check as CheckIcon, TriangleAlert, X } from 'lucide-react'
import type { Check } from '../api/types'

export function Checklist({ checks }: { checks: Check[] }) {
  return (
    <ul className="space-y-2">
      {checks.map((check) => (
        <li key={check.rule} className="flex gap-2.5 text-[15px] leading-snug">
          <CheckMark check={check} />
          <span className={check.ok && !check.warning ? '' : 'font-medium'}>
            {check.text}
          </span>
        </li>
      ))}
    </ul>
  )
}

const MARKS = {
  failed: { icon: X, tile: 'bg-error/10 text-error', label: 'Not met:' },
  warning: {
    icon: TriangleAlert,
    tile: 'bg-warning/12 text-warning',
    label: 'Note:',
  },
  met: { icon: CheckIcon, tile: 'bg-success/12 text-success', label: 'Met:' },
}

function CheckMark({ check }: { check: Check }) {
  const mark = !check.ok
    ? MARKS.failed
    : check.warning
      ? MARKS.warning
      : MARKS.met
  const Icon = mark.icon
  return (
    <>
      <span aria-hidden className={`icon-tile size-5 ${mark.tile}`}>
        <Icon className="size-3" strokeWidth={3} />
      </span>
      <span className="sr-only">{mark.label}</span>
    </>
  )
}
