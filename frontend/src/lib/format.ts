// Display formatting (ui.md §3). Money arrives as decimal strings and is never turned
// into floating-point numbers: it is only re-written for display.

const MINUS = '−'
const MINUTE_MS = 60_000
const HOUR_MS = 60 * MINUTE_MS
const DAY_MS = 24 * HOUR_MS
const SMALLEST_COST_SHOWN = 0.001

const dayFormat = new Intl.DateTimeFormat('en-US', {
  weekday: 'short',
  month: 'short',
  day: 'numeric',
})
const timeFormat = new Intl.DateTimeFormat('en-US', {
  hour: 'numeric',
  minute: '2-digit',
})

export function formatMoney(amount: string): string {
  const negative = amount.startsWith('-')
  const [whole = '0', cents = ''] = amount.replace('-', '').split('.')
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return `${negative ? MINUS : ''}$${grouped}.${cents.padEnd(2, '0').slice(0, 2)}`
}

// "2026-09-14" and naive "2026-09-15T08:12:44" are wall-clock times at the credit
// union: read them as local times so they print exactly as stored.
function toDate(iso: string): Date {
  const dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(iso)
  return new Date(dateOnly ? `${iso}T00:00:00` : iso)
}

export function formatDay(iso: string): string {
  return dayFormat.format(toDate(iso))
}

export function formatTime(iso: string): string {
  return timeFormat.format(toDate(iso))
}

export function formatReceived(iso: string): string {
  return `${formatDay(iso)}, ${formatTime(iso)}`
}

export function relativeTime(iso: string, now: Date): string {
  const elapsed = now.getTime() - toDate(iso).getTime()
  if (elapsed < MINUTE_MS) return 'just now'
  if (elapsed < HOUR_MS) return `${Math.floor(elapsed / MINUTE_MS)} min ago`
  if (elapsed < DAY_MS) return `${Math.round(elapsed / HOUR_MS)} h ago`
  const days = Math.floor(elapsed / DAY_MS)
  return `${days} ${days === 1 ? 'day' : 'days'} ago`
}

export function formatDuration(ms: number): string {
  return `${(ms / 1000).toFixed(1)} s`
}

// Run costs are tiny observability figures, not money that moves.
export function formatCost(usd: string): string {
  const value = Number(usd)
  if (value < SMALLEST_COST_SHOWN) return `<$${SMALLEST_COST_SHOWN}`
  return `$${value.toFixed(3)}`
}
