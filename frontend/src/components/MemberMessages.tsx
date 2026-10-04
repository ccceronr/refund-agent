// What the member wrote (ui.md §2.5), always as plain text. A thread shows every message;
// the member's are tinted terracotta, the credit union's grey.
import { Mail } from 'lucide-react'
import type { Message } from '../api/types'
import { formatDay, formatTime, initials } from '../lib/format'

export function MemberMessages({
  messages,
  firstName,
}: {
  messages: Message[]
  firstName: string
}) {
  if (messages.length === 0) return null
  return (
    <section aria-labelledby="messages" className="card p-5">
      <header className="flex items-center gap-3">
        <span aria-hidden className="icon-tile bg-terracotta/14 text-navy">
          <Mail className="size-4" />
        </span>
        <h2 id="messages" className="font-semibold">
          {messages.length > 1 ? 'Conversation' : `${firstName} wrote`}
        </h2>
      </header>
      <ol className="mt-3 space-y-3">
        {messages.map((message) => (
          <MessageBubble
            key={`${message.sent_at}-${message.author_name}`}
            message={message}
          />
        ))}
      </ol>
    </section>
  )
}

function MessageBubble({ message }: { message: Message }) {
  const fromMember = message.from === 'member'
  return (
    <li
      className={`flex gap-3 rounded-xl px-4 py-3.5 ${fromMember ? 'bg-terracotta/8' : 'ml-8 bg-grey-50'}`}
    >
      <span
        aria-hidden
        className={`flex size-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${fromMember ? 'bg-terracotta/20' : 'bg-navy/8'}`}
      >
        {initials(message.author_name)}
      </span>
      <figure className="min-w-0 flex-1">
        <figcaption className="flex flex-wrap items-baseline justify-between gap-x-3 text-sm">
          <span className="font-semibold">{message.author_name}</span>
          <span className="text-xs text-grey-600">
            {formatDay(message.sent_at)}, {formatTime(message.sent_at)}
          </span>
        </figcaption>
        <blockquote className="mt-0.5 whitespace-pre-line">
          {message.body}
        </blockquote>
      </figure>
    </li>
  )
}
