// The open case (ui.md §2.2–§2.8): prepared on open when new (R-03), decided from the card
// next to it.
import { motion } from 'motion/react'
import { type ReactNode, useCallback, useEffect, useRef, useState } from 'react'
import { useCase } from '../api/hooks'
import type { CaseDetail, Proposal, Role } from '../api/types'
import { useCaseRun } from '../hooks/useCaseRun'
import { useAskSupervisor } from '../hooks/useAskSupervisor'
import { useDecision } from '../hooks/useDecision'
import { availableActions, canAskSupervisor } from '../lib/actions'
import {
  decisionBody,
  decisionChoices,
  isChanged,
  type DecisionChoices,
  type Outcome,
} from '../lib/decision'
import { hasEvidence } from '../lib/evidence'
import { CaseHeader } from './CaseHeader'
import { DecisionCard } from './DecisionCard'
import { DecisionOptions } from './DecisionOptions'
import { EvidencePanel } from './EvidencePanel'
import { MemberMessages } from './MemberMessages'
import { RecommendationCard } from './RecommendationCard'
import type { OpenPolicy } from './PolicyQuote'
import { PreparedCard } from './PreparedCard'
import { ReplyEditor } from './ReplyEditor'
import { RunProgress } from './RunProgress'

interface CaseViewProps {
  caseId: number
  role: Role
  onOpenPolicy: OpenPolicy
  onNext: (() => void) | null
}

export function CaseView({
  caseId,
  role,
  onOpenPolicy,
  onNext,
}: CaseViewProps) {
  const detail = useCase(caseId)
  const [run, startRun] = useCaseRun(caseId)
  const autoStarted = useRef(false)
  const isNew = detail.data?.status === 'new'

  // R-03: a case nobody has prepared yet is prepared as soon as it is opened.
  useEffect(() => {
    if (isNew && !autoStarted.current) {
      autoStarted.current = true
      startRun()
    }
  }, [isNew, startRun])

  if (detail.isPending) return <CaseSkeleton />
  if (detail.error) {
    return (
      <p role="alert" className="px-6 py-10 text-error lg:px-10">
        {detail.error.message}
      </p>
    )
  }
  const showRun = run.phase !== 'idle' || detail.data.status === 'new'
  return (
    <CaseContent
      key={detail.data.proposal?.draft_reply ?? 'none'}
      detail={detail.data}
      role={role}
      progress={showRun ? <RunProgress run={run} onRetry={startRun} /> : null}
      running={run.phase === 'running'}
      onRunAgain={startRun}
      onOpenPolicy={onOpenPolicy}
      onNext={onNext}
    />
  )
}

function CaseSkeleton() {
  return (
    <div
      aria-busy="true"
      className="mx-auto max-w-6xl px-4 pt-6 sm:px-6 lg:px-8 lg:pt-8"
    >
      <span className="sr-only">Opening the conversation…</span>
      <div className="flex items-center gap-4">
        <div className="skeleton size-12 rounded-full" />
        <div className="flex-1 space-y-2">
          <div className="skeleton h-7 w-1/3" />
          <div className="skeleton h-4 w-1/2" />
        </div>
      </div>
      <div className="mt-6 grid gap-6 @4xl:grid-cols-[minmax(0,1fr)_26rem]">
        <div className="space-y-6">
          <div className="card h-36 p-6">
            <div className="skeleton h-4 w-2/3" />
          </div>
          <div className="card h-56 p-6">
            <div className="skeleton h-4 w-1/2" />
          </div>
        </div>
        <div className="card space-y-3 p-6 max-@4xl:order-first">
          <div className="skeleton h-7 w-3/4" />
          <div className="skeleton h-4 w-1/2" />
          <div className="skeleton mt-5 h-4 w-5/6" />
          <div className="skeleton h-4 w-4/6" />
        </div>
      </div>
    </div>
  )
}

interface CaseContentProps {
  detail: CaseDetail
  role: Role
  progress: ReactNode
  running: boolean
  onRunAgain: () => void
  onOpenPolicy: OpenPolicy
  onNext: (() => void) | null
}

function CaseContent({
  detail,
  role,
  progress,
  running,
  onRunAgain,
  onOpenPolicy,
  onNext,
}: CaseContentProps) {
  const firstName = detail.member.name.split(' ')[0] ?? detail.member.name
  const decision = useDecision(detail.id)
  const askSupervisor = useAskSupervisor(detail.id)
  const draft = useDraft(detail.proposal, role)
  const actions = availableActions(detail, role, draft.state)
  const proposal = progress ? null : detail.proposal
  const deciding =
    proposal !== null &&
    (actions.primary !== null || decision.result !== undefined)

  const submit = useCallback(() => {
    if (detail.proposal)
      decision.decide(decisionBody(detail.proposal, draft.values))
  }, [decision, detail.proposal, draft.values])

  const decisionCard = deciding && (
    <DecisionCard
      detail={detail}
      actions={actions}
      pending={decision.isPending}
      error={decision.error ?? askSupervisor.error}
      result={decision.result}
      onPrimary={submit}
      onReject={(reason) => decision.decide({ action: 'reject', reason })}
      canAskSupervisor={canAskSupervisor(detail, role)}
      asking={askSupervisor.isPending}
      onAskSupervisor={askSupervisor.ask}
      onNext={onNext}
    >
      <DecisionOptions
        choices={draft.choices}
        feeChoices={proposal.fee_choices}
        outcome={draft.values.outcome}
        feeId={draft.values.feeId}
        onOutcome={draft.setOutcome}
        onFee={draft.setFeeId}
      />
    </DecisionCard>
  )

  return (
    <CaseLayout
      header={<CaseHeader detail={detail} />}
      recommendation={
        progress ?? (
          <RecommendationCard detail={detail} onOpenPolicy={onOpenPolicy} />
        )
      }
      evidence={
        <>
          {proposal &&
            detail.evidence &&
            hasEvidence(detail.evidence, proposal) && (
              <EvidencePanel
                evidence={detail.evidence}
                proposal={proposal}
                standing={detail.member.standing}
              />
            )}
          {/* R-17 for audit: Luis doesn't need the run figures, a supervisor might. */}
          {role === 'supervisor' && !progress && detail.run && (
            <PreparedCard
              run={detail.run}
              canRunAgain={proposal !== null && !isDecided(detail)}
              busy={running || decision.isPending}
              onRunAgain={onRunAgain}
            />
          )}
        </>
      }
      conversation={
        <>
          <MemberMessages messages={detail.messages} firstName={firstName} />
          {proposal && actions.primary && (
            <ReplyEditor
              proposal={proposal}
              firstName={firstName}
              value={draft.values.reply}
              onChange={draft.setReply}
            />
          )}
        </>
      }
      decision={decisionCard}
    />
  )
}

function isDecided(detail: CaseDetail): boolean {
  return detail.status === 'resolved' || detail.status === 'auto_resolved'
}

interface CaseLayoutProps {
  header: ReactNode
  recommendation: ReactNode
  evidence: ReactNode
  conversation: ReactNode
  decision: ReactNode
}

// Two columns when the case area is wide enough: on the left, why (the recommendation and
// the evidence); on the right, what to do (the message, the reply and the decision), which
// stays in view while Luis scrolls and scrolls on its own if taller than the window.
// Narrower, one column in the order Luis needs it: recommendation, message, reply,
// decision, then the evidence.
function CaseLayout(props: CaseLayoutProps) {
  return (
    <motion.article
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: 'easeOut' }}
      className="mx-auto max-w-6xl px-4 pt-6 pb-16 sm:px-6 lg:px-8 lg:pt-8"
    >
      {props.header}
      <div className="mt-6 grid gap-6 @4xl:grid-cols-[minmax(0,1fr)_28rem] @4xl:items-start">
        <div className="flex min-w-0 flex-col gap-6 @max-4xl:contents">
          <div className="@max-4xl:order-1">{props.recommendation}</div>
          <div className="flex flex-col gap-6 empty:hidden @max-4xl:order-4">
            {props.evidence}
          </div>
        </div>
        <div className="flex flex-col gap-4 @max-4xl:contents @4xl:sticky @4xl:top-6 @4xl:-m-1 @4xl:max-h-[calc(100dvh-3rem)] @4xl:overflow-y-auto @4xl:p-1">
          <div className="flex flex-col gap-4 @max-4xl:order-2">
            {props.conversation}
          </div>
          {props.decision && (
            <div className="@max-4xl:order-3">{props.decision}</div>
          )}
        </div>
      </div>
    </motion.article>
  )
}

const NO_PROPOSAL_CHOICES: DecisionChoices = {
  outcomes: [],
  proposed: 'no_refund',
  needsFeePick: false,
}

function useDraft(proposal: Proposal | null, role: Role) {
  const choices = proposal
    ? decisionChoices(proposal, role)
    : NO_PROPOSAL_CHOICES
  const [outcome, setOutcome] = useState<Outcome>(choices.proposed)
  const [reply, setReply] = useState(proposal?.draft_reply ?? '')
  const [feeId, setFeeId] = useState<number | null>(null)
  const values = { outcome, reply, feeId }
  const state = {
    changed: proposal ? isChanged(proposal, values, choices.proposed) : false,
    outcome,
    feeMissing: choices.needsFeePick && outcome === 'refund' && feeId === null,
  }
  return { choices, values, state, setOutcome, setReply, setFeeId }
}
