// The left column (ui.md §2): the product, the queue, and who is signed in (the one navy
// block, so it reads as "you").
import { House, LogOut } from 'lucide-react'
import { useSignOut } from '../api/hooks'
import type { Staff } from '../api/types'
import { initials } from '../lib/format'
import { ProductMark } from './Brand'
import { Queue } from './Queue'

const ROLE_LABELS = { staff: 'Staff', supervisor: 'Supervisor' } as const

interface SidebarProps {
  staff: Staff
  selectedId: number | null
  onSelect: (id: number) => void
  onOverview: () => void
}

export function Sidebar({
  staff,
  selectedId,
  onSelect,
  onOverview,
}: SidebarProps) {
  return (
    <div className="flex h-full flex-col border-r border-navy/8 bg-clay">
      <div className="flex h-16 shrink-0 items-center gap-3 px-5">
        <ProductMark />
        <span className="text-lg font-semibold tracking-tight">
          Member messages
        </span>
      </div>
      <OverviewLink current={selectedId === null} onOpen={onOverview} />
      <div className="min-h-0 flex-1 overflow-y-auto">
        <Queue role={staff.role} selectedId={selectedId} onSelect={onSelect} />
      </div>
      <SignedIn staff={staff} />
    </div>
  )
}

// The way back to the overview from any case (desktop: on a narrow screen the list itself
// is the overview, and "Back to list" leads there).
function OverviewLink({
  current,
  onOpen,
}: {
  current: boolean
  onOpen: () => void
}) {
  return (
    <div className="px-2 pb-2 max-lg:hidden">
      <button
        type="button"
        aria-current={current ? 'page' : undefined}
        onClick={onOpen}
        className={`relative flex w-full cursor-pointer items-center gap-2.5 rounded-xl px-3 py-2.5 font-medium transition-colors duration-150 ${
          current ? 'bg-white' : 'hover:bg-white/60 active:bg-white'
        }`}
      >
        {current && (
          <span
            aria-hidden
            className="absolute inset-y-2.5 left-0 w-[3px] rounded-full bg-terracotta"
          />
        )}
        <House aria-hidden className="size-4" />
        Overview
      </button>
    </div>
  )
}

function SignedIn({ staff }: { staff: Staff }) {
  const signOut = useSignOut()
  return (
    <div className="m-3 flex shrink-0 items-center gap-3 rounded-2xl bg-navy px-4 py-3 text-white">
      <span
        aria-hidden
        className="flex size-9 items-center justify-center rounded-full bg-white/12 text-sm font-semibold"
      >
        {initials(staff.name)}
      </span>
      <span className="min-w-0 flex-1 leading-tight">
        <span className="block truncate font-medium">{staff.name}</span>
        <span className="block text-[13px] text-white/70">
          {ROLE_LABELS[staff.role]}
        </span>
      </span>
      <button
        type="button"
        onClick={() => signOut.mutate()}
        className="button h-9 px-3 text-sm text-white/80 hover:bg-white/10 hover:text-white active:bg-white/15"
      >
        <LogOut aria-hidden className="size-4" />
        Sign out
      </button>
    </div>
  )
}
