// The product mark: a navy tile with the inbox, next to the product name.
import { Inbox } from 'lucide-react'

export function ProductMark() {
  return (
    <span
      aria-hidden
      className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-navy text-white"
    >
      <Inbox className="size-5" strokeWidth={2.25} />
    </span>
  )
}
