// The reply (ui.md §2.6), prefilled with the draft. Editing it switches the primary action
// to "Send edited reply"; "Restore suggested reply" puts the draft back.
import { PenLine, RotateCcw } from 'lucide-react'
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
  const suggested = proposal.draft_reply
  const edited = suggested !== null && value !== suggested
  return (
    <section className="card p-5">
      <header className="flex min-h-9 flex-wrap items-center gap-3">
        <span aria-hidden className="icon-tile bg-navy/8 text-navy">
          <PenLine className="size-4" />
        </span>
        <label htmlFor="reply" className="font-semibold">
          Reply to {firstName} ({language})
        </label>
        {edited && (
          <button
            type="button"
            onClick={() => onChange(suggested)}
            className="button-quiet ml-auto h-8 text-sm"
          >
            <RotateCcw aria-hidden className="size-3.5" />
            Restore suggested reply
          </button>
        )}
      </header>
      <textarea
        id="reply"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        rows={6}
        maxLength={MAX_REPLY_CHARS}
        aria-describedby="reply-help"
        className="field mt-3 resize-y bg-grey-50/60 p-4 leading-relaxed focus:bg-white"
      />
      <p
        id="reply-help"
        className="mt-1.5 flex justify-between gap-4 text-sm text-grey-600"
      >
        <span>
          {proposal.draft_source === 'template' &&
            'Written from a standard template.'}
        </span>
        <span className="tabular-nums">
          {value.length} / {MAX_REPLY_CHARS}
        </span>
      </p>
    </section>
  )
}
