// One look per queue section, shared by the queue, the overview cards and the status chip
// (ui.md §1): terracotta means "needs attention", the status colors mean what they say.
import {
  CircleCheck,
  Clock,
  Eye,
  Inbox,
  type LucideIcon,
  MessageSquare,
  ShieldAlert,
} from 'lucide-react'
import type { SectionKey } from '../lib/queue'

interface SectionStyle {
  icon: LucideIcon
  tint: string // soft background for tiles and chips (text on it stays navy)
  ink: string // icon color on that background
}

export const SECTION_STYLES: Record<SectionKey, SectionStyle> = {
  ready: { icon: Inbox, tint: 'bg-navy/8', ink: 'text-navy' },
  new: { icon: Clock, tint: 'bg-grey-100', ink: 'text-grey-600' },
  review: { icon: Eye, tint: 'bg-terracotta/14', ink: 'text-terracotta' },
  supervisor: { icon: ShieldAlert, tint: 'bg-warning/12', ink: 'text-warning' },
  not_refund: {
    icon: MessageSquare,
    tint: 'bg-grey-100',
    ink: 'text-grey-600',
  },
  done: { icon: CircleCheck, tint: 'bg-success/12', ink: 'text-success' },
}
