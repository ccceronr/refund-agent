// The reply (ui.md §2.6), prefilled with the draft. Sending arrives with the actions (P7b).
import type { Proposal } from '../api/types'

const LANGUAGES = { en: 'English', es: 'Spanish' } as const
const MAX_REPLY_CHARS = 2000

interface ReplyEditorProps {
  proposal: Proposal
  firstName: string
  value: string
  onChange: (text: string) => void
}

export function ReplyEditor({
  proposal,
  firstName,
  value,
  onChange,
}: ReplyEditorProps) {
  const language = LANGUAGES[proposal.language ?? 'en']
  return (
    <section>
      <label
        htmlFor="reply"
        className="text-xs font-semibold tracking-wide text-grey-500 uppercase"
      >
        Reply to {firstName} ({language})
      </label>
      <textarea
        id="reply"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        rows={8}
        maxLength={MAX_REPLY_CHARS}
        className="mt-2 w-full resize-y rounded-xl border border-grey-200 bg-white p-4 leading-relaxed"
      />
      {proposal.draft_source === 'template' && (
        <p className="mt-1 text-sm text-grey-500">
          Written from a standard template.
        </p>
      )}
    </section>
  )
}
