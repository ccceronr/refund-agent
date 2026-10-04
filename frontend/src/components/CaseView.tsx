// The open case (ui.md §2.2–§2.8): prepared on open when new (R-03), decided from the bar.
import { motion } from 'motion/react'
import { type ReactNode, useCallback, useEffect, useRef, useState } from 'react'
import { useCase } from '../api/hooks'
import type { CaseDetail, Proposal, Role } from '../api/types'
import { useCaseRun } from '../hooks/useCaseRun'
import { useDecision } from '../hooks/useDecision'
import { availableActions } from '../lib/actions'
import {
  decisionBody,
  decisionChoices,
  isChanged,
  type DecisionChoices,
  type Outcome,
} from '../lib/decision'
import { hasEvidence } from '../lib/evidence'
import { ActionBar } from './ActionBar'
import { CaseHeader } from './CaseHeader'
import { DecisionOptions } from './DecisionOptions'
import { EvidencePanel } from './EvidencePanel'
import { MemberMessages } from './MemberMessages'
import { RecommendationCard } from './RecommendationCard'
import type { OpenPolicy } from './PolicyQuote'
import { ReplyEditor } from './ReplyEditor'
import { RunProgress } from './RunProgress'

interface CaseViewProps {
  caseId: number
  role: Role
  onOpenPolicy: OpenPolicy
}

export function CaseView({ caseId, role, onOpenPolicy }: CaseViewProps) {
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

  if (detail.isPending)
    return <p className="px-8 py-10 text-grey-500">Opening the conversation…</p>
  if (detail.error) {
    return (
      <p role="alert" className="px-8 py-10 text-error">
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
    />
  )
}

interface CaseContentProps {
  detail: CaseDetail
  role: Role
  progress: ReactNode
  running: boolean
  onRunAgain: () => void
  onOpenPolicy: OpenPolicy
}

function CaseContent({
  detail,
  role,
  progress,
  running,
  onRunAgain,
  onOpenPolicy,
}: CaseContentProps) {
  const firstName = detail.member.name.split(' ')[0] ?? detail.member.name
  const decision = useDecision(detail.id)
  const draft = useDraft(detail.proposal, role)
  const actions = availableActions(detail, role, draft.state)

  const submit = useCallback(() => {
    if (detail.proposal)
      decision.decide(decisionBody(detail.proposal, draft.values))
  }, [decision, detail.proposal, draft.values])

  return (
    <>
      <motion.article
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.2, ease: 'easeOut' }}
        className="mx-auto max-w-3xl space-y-6 px-6 pt-8 pb-40 lg:px-10"
      >
        <CaseHeader detail={detail} />
        {progress ?? (
          <RecommendationCard detail={detail} onOpenPolicy={onOpenPolicy} />
        )}
        {!progress &&
          detail.evidence &&
          hasEvidence(detail.evidence, detail.proposal) && (
            <EvidencePanel
              evidence={detail.evidence}
              proposal={detail.proposal}
              standing={detail.member.standing}
            />
          )}
        <MemberMessages messages={detail.messages} firstName={firstName} />
        {!progress && detail.proposal && actions.primary && (
          <>
            <DecisionOptions
              choices={draft.choices}
              feeChoices={detail.proposal.fee_choices}
              outcome={draft.values.outcome}
              feeId={draft.values.feeId}
              onOutcome={draft.setOutcome}
              onFee={draft.setFeeId}
            />
            <ReplyEditor
              proposal={detail.proposal}
              firstName={firstName}
              value={draft.values.reply}
              onChange={draft.setReply}
            />
          </>
        )}
      </motion.article>
      {!progress && (
        <ActionBar
          detail={detail}
          actions={actions}
          pending={decision.isPending}
          error={decision.error}
          result={decision.result}
          running={running}
          onPrimary={submit}
          onReject={(reason) => decision.decide({ action: 'reject', reason })}
          onRunAgain={onRunAgain}
        />
      )}
    </>
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
