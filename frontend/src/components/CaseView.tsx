// The open case (ui.md §2.2–§2.7). Actions and live runs arrive in P7b.
import { motion } from 'motion/react'
import { useState } from 'react'
import { useCase } from '../api/hooks'
import type { CaseDetail, Role } from '../api/types'
import { ActionBar } from './ActionBar'
import { CaseHeader } from './CaseHeader'
import { hasEvidence } from '../lib/evidence'
import { EvidencePanel } from './EvidencePanel'
import { MemberMessages } from './MemberMessages'
import { RecommendationCard } from './RecommendationCard'
import { ReplyEditor } from './ReplyEditor'

export function CaseView({ caseId, role }: { caseId: number; role: Role }) {
  const detail = useCase(caseId)

  if (detail.isPending)
    return <p className="px-8 py-10 text-grey-500">Opening the conversation…</p>
  if (detail.error) {
    return (
      <p role="alert" className="px-8 py-10 text-error">
        {detail.error.message}
      </p>
    )
  }
  return <CaseContent detail={detail.data} role={role} />
}

function CaseContent({ detail, role }: { detail: CaseDetail; role: Role }) {
  const firstName = detail.member.name.split(' ')[0] ?? detail.member.name
  const draft = detail.proposal?.draft_reply ?? ''
  const [reply, setReply] = useState(draft)

  return (
    <>
      <motion.article
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.2, ease: 'easeOut' }}
        className="mx-auto max-w-3xl space-y-6 px-6 pt-8 pb-32 lg:px-10"
      >
        <CaseHeader detail={detail} />
        <RecommendationCard detail={detail} />
        {detail.evidence && hasEvidence(detail.evidence, detail.proposal) && (
          <EvidencePanel
            evidence={detail.evidence}
            proposal={detail.proposal}
            standing={detail.member.standing}
          />
        )}
        <MemberMessages messages={detail.messages} firstName={firstName} />
        {detail.proposal && (
          <ReplyEditor
            proposal={detail.proposal}
            firstName={firstName}
            value={reply}
            onChange={setReply}
          />
        )}
      </motion.article>
      <ActionBar detail={detail} role={role} edited={reply !== draft} />
    </>
  )
}
