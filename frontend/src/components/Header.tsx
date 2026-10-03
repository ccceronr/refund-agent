import { useSignOut } from '../api/hooks'
import type { Staff } from '../api/types'

const ROLE_LABELS = { staff: 'Staff', supervisor: 'Supervisor' } as const

export function Header({ staff }: { staff: Staff }) {
  const signOut = useSignOut()

  return (
    <header className="flex items-center justify-between border-b border-grey-200 bg-white px-6 py-3">
      <span className="font-serif text-xl">Member messages</span>
      <div className="flex items-center gap-4 text-sm">
        <span>
          {staff.name}{' '}
          <span className="text-grey-500">({ROLE_LABELS[staff.role]})</span>
        </span>
        <button
          type="button"
          onClick={() => signOut.mutate()}
          className="rounded-md px-2 py-1 text-grey-600 hover:bg-grey-100 hover:text-navy"
        >
          Sign out
        </button>
      </div>
    </header>
  )
}
