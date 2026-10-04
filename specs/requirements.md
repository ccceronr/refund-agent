# Requirements

Format: EARS ("When <trigger>, the system shall <response>"). Each requirement has an ID
used in code comments, tests and commits. Source: the Blossom technical test PDF.

## Context
Luis, a credit union employee, answers member messages in Magic (back-office tool). Today a
fee refund request takes ~8 manual steps across two systems. This system prepares each case
(understands the message, gathers the evidence, applies the policy, drafts the reply) so
Luis can make the final call in seconds, and resolves clean cases on its own (tiered
autonomy, BR-08).

A **case** is one customer conversation (`conversations` row).

## Functional

### Queue and case
- **R-01** The system shall list open cases (conversation status ≠ `closed`, plus cases
  resolved in the last 24 h) ordered by oldest waiting first, each with member first name,
  a plain topic label, received time and a plain status label.
- **R-02** When Luis opens a case, the system shall show, on one page: the member's
  messages, the recommendation, the reasons, the evidence, the policy quote, the draft reply
  and the available actions.
- **R-03** When Luis opens a case that has never been prepared, the UI shall start the agent
  run automatically and show each step live (R-16). Staff can also prepare every new case
  at once ("Prepare new messages"): the server runs them one by one, within the run
  limits, and the AUTO tier refunds where it applies, without anyone opening the case.
  (In production the agent would run when each message arrives.)

### Agent flow
- **R-04** When a run starts, the system shall screen the member's message for prompt
  injection, intent, language and tone in one typed-decision call (Jev).
- **R-05** If injection probability ≥ `INJECTION_THRESHOLD`, the system shall stop the run
  and send the case to manual review (`INJECTION_SUSPECTED`).
- **R-06** If the intent is not a fee refund with confidence ≥ `DECISION_MIN_CONFIDENCE`,
  the system shall mark the case `not_refund`; if the intent is unclear or below the
  threshold, manual review (`INTENT_UNCLEAR`).
- **R-07** When the intent is a fee refund, the system shall gather the evidence with
  read-only tools: member accounts, fee candidates, same-day postings in posting order,
  refund history in the window, and member standing.
- **R-08** The system shall identify the fee: 0 candidates → manual (`NO_FEE_FOUND`);
  1 candidate → that fee; more than 1 → Jev picks one; if confidence <
  `DECISION_MIN_CONFIDENCE` or Jev answers "unclear" → manual (`AMBIGUOUS_FEE`).
- **R-09** The system shall evaluate BR-01…BR-08 and save a proposal: recommendation,
  reason code, every check with its result, tier, refunds left and amount.
- **R-10** The system shall retrieve the policy passage that supports the outcome and
  show it as an exact quote with the document title.
- **R-11** The system shall draft a reply in the member's language (English or Spanish)
  and matching tone, consistent with the recommendation.
- **R-12** The system shall check the draft before saving it (output guard, design §7.5);
  if it fails, use the template reply for that outcome and language.
- **R-13** When the tier is `AUTO`, the system shall execute the refund (BR-11), send the
  reply and close the conversation (BR-12) without staff action.

### Decisions
- **R-14** When staff submits a decision (approve, edit or reject), the system shall apply
  BR-09…BR-12 and record who, when, what and why.
- **R-15** The decision endpoint shall be idempotent: the same `Idempotency-Key` returns
  the original result; a second different decision on a decided case returns 409; a fee can
  never be refunded twice (DB unique constraint).

### Visibility
- **R-16** The UI shall show each agent step live while it runs (SSE), in plain language.
- **R-17** The UI shall show the cost and duration of the latest run per case.

## Failure handling
- **R-18** Every LLM and Jev call shall have a timeout and retries with exponential
  backoff on 429/5xx/529 (and Anthropic 529).
- **R-19** When Jev fails after retries, the system shall answer the same typed questions
  with the fast model (Haiku); fallback answers can never qualify for AUTO.
- **R-20** When both Jev and Haiku fail, or the writer fails and the template cannot be
  used, or the whole run exceeds `RUN_TIMEOUT_SECONDS` (90), the case shall go to manual
  review with the reason shown to Luis (`AI_UNAVAILABLE`, `TIMEOUT`).
- **R-21** The API shall validate every input and return friendly error messages
  (`{"error": {"code", "message"}}`), never stack traces.
- **R-22** The API shall rate-limit requests (60/min per client; 10/min on `/run`).

## Learning and quality
- **R-23** When staff edits a draft (changes reply or outcome) or rejects a proposal, the
  system shall store the case as a feedback eval with the staff's outcome as expected.
- **R-24** An eval script shall run ≥ 15 cases (refund, no refund, edge cases) and print
  pass rate per check, plus cost per case and savings vs. an all-Sonnet baseline.

## Non-functional
- **R-30 State:** cases, runs, steps, proposals, decisions and refunds persist in Postgres
  and survive a restart.
- **R-31 Read-only agents:** agent tools connect with the `agent_ro` DB user (SELECT only).
- **R-32 Secrets:** only from environment variables.
- **R-33 Privacy:** no personal data in logs; prompts receive only what each step needs
  (design §8); account numbers masked as `••4210` everywhere except the evidence panel.
- **R-34 Observability:** structured JSON logs with a request id; latency, tokens and cost
  per agent step and per tool call stored in `agent_steps`.
- **R-35 Audit:** every proposal, decision, refund and status change writes to
  `audit_log` (who, when, what, why).
- **R-36 Packaging:** `docker compose up` starts db, migrations, seed, backend, frontend.
- **R-37 Quality gates:** pre-commit (ruff lint + format, mypy, ESLint, Prettier); CI runs
  them plus tests.
- **R-38 Tests:** unit tests for data queries and decision rules, one API test (decision
  idempotency), Vitest for UI logic, Playwright for the happy path and one failure.

- **R-39 Authentication:** every endpoint except `/health` and `/auth/login` requires a
  signed-in staff member (design §4.0); the decision actor comes only from the session.
- **R-40 OWASP:** the app addresses the OWASP Top 10:2025 and the OWASP Top 10 for LLM
  Applications 2025 as mapped in CLAUDE.md; the README includes that mapping.
- **R-41 Bounded consumption:** member text sent to models is truncated to
  `MAX_MESSAGE_CHARS_FOR_MODELS`; a case can be run at most `MAX_RUNS_PER_CASE_PER_HOUR`
  times; every model call has `max_tokens` and a timeout.

## Bonus (in priority order; see tasks.md)
Jev (R-04, R-08, R-10) · Evals (R-24) · Prompt injection (R-05, §7.5) · Policy RAG (R-10) ·
Audit (R-35) · Observability (R-34) · Personal data (R-33) · Feedback loop (R-23) ·
Model per step (CLAUDE.md models) · Customer language (R-11) · Streaming (R-16) ·
Cost (R-17, prompt caching) · MCP server (task P11) · E2E tests (R-38) · Deployment on Railway (P9).
