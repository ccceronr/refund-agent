// The API contract (design §4.1, §4.2). Money and amounts are strings ("35.00").

export type Role = 'staff' | 'supervisor'

export interface Staff {
  name: string
  role: Role
}

export type CaseStatus =
  | 'new'
  | 'running'
  | 'ready'
  | 'needs_supervisor'
  | 'manual_review'
  | 'not_refund'
  | 'auto_resolved'
  | 'resolved'

export type Tier = 'AUTO' | 'STAFF' | 'SUPERVISOR' | 'MANUAL'
export type Recommendation = 'REFUND' | 'NO_REFUND' | 'MANUAL'

export interface CaseListItem {
  id: number
  member_name: string
  topic: string
  status: CaseStatus
  status_label: string
  received_at: string
  tier: Tier | null
}

export interface Member {
  name: string
  standing: 'good' | 'not_good'
  credit_union: string
}

export interface Message {
  from: 'member' | 'staff'
  author_name: string
  body: string
  sent_at: string
}

export interface Check {
  rule: string
  ok: boolean
  text: string
  warning: boolean
}

export interface PolicyQuote {
  document: string
  text: string
  slug: string
  passage_id: number
}

export interface FeeChoice {
  id: number
  label: string
}

export interface Proposal {
  recommendation: Recommendation
  reason_code: string
  tier: Tier
  headline: string
  authority_note: string | null
  amount: string | null
  checks: Check[]
  policy_quote: PolicyQuote | null
  draft_reply: string | null
  draft_source: 'writer' | 'template' | null
  language: 'en' | 'es' | null
  manual_reason: string | null
  fee_choices: FeeChoice[]
}

export interface Fee {
  label: string
  amount: string
  date: string
  sub_account: string
  account: string
  account_number_full: string | null
}

export interface Posting {
  order: number
  description: string
  raw_description: string
  amount: string
  balance_after: string
  is_fee: boolean
}

export interface Refund {
  date: string
  label: string
  amount: string
}

export interface Evidence {
  fee: Fee | null
  day_postings: Posting[]
  refund_history: Refund[]
  refunds_used: number | null
  refunds_limit: number
}

export interface RunStep {
  label: string
  status: 'running' | 'done' | 'failed'
  duration_ms: number | null
}

export interface Run {
  status: 'running' | 'completed' | 'failed'
  duration_ms: number
  cost_usd: string
  steps: RunStep[]
}

export interface DecisionSummary {
  action: 'approve' | 'edit' | 'reject'
  outcome: 'refund' | 'no_refund' | 'none'
  by: string
  at: string
}

export interface CaseDetail {
  id: number
  status: CaseStatus
  status_label: string
  topic: string
  received_at: string
  member: Member
  messages: Message[]
  proposal: Proposal | null
  evidence: Evidence | null
  run: Run | null
  decision: DecisionSummary | null
}

export interface PolicyDocument {
  slug: string
  title: string
  passages: { id: number; text: string }[]
}
