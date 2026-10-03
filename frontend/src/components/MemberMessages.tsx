// What the member wrote (ui.md §2.5), always as plain text.
import type { Message } from '../api/types'
import { formatDay, formatTime } from '../lib/format'

export function MemberMessages({
  messages,
  firstName,
}: {
  messages: Message[]
  firstName: string
}) {
  if (messages.length === 0) return null
  const thread = messages.length > 1
  return (
    <section aria-label="Messages" className="space-y-3">
      {!thread && <h3 className="text-sm text-grey-500">{firstName} wrote:</h3>}
      {messages.map((message) => (
        <figure
          key={`${message.sent_at}-${message.author_name}`}
          className={`rounded-xl px-5 py-3 ${message.from === 'member' ? 'bg-white' : 'ml-10 bg-grey-100'}`}
        >
          {thread && (
            <figcaption className="text-sm font-medium">
              {message.author_name}
            </figcaption>
          )}
          <blockquote className="whitespace-pre-line">
            {message.body}
          </blockquote>
          <p className="mt-1 text-xs text-grey-500">
            {formatDay(message.sent_at)}, {formatTime(message.sent_at)}
          </p>
        </figure>
      ))}
    </section>
  )
}
