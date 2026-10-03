# CLAUDE.md — Fee Refund Agent (Blossom technical test)

You are building a working app for a technical test. The specs in `specs/` are the
**source of truth**. Read them before writing code, and re-read the relevant spec before
each phase.

## Read order
1. `specs/requirements.md` — what the system must do (R-xx IDs)
2. `specs/business-rules.md` — refund rules (BR-xx IDs). **Never invent or change a rule.**
3. `specs/design.md` — architecture, data model, API contract, agent graph, prompts
4. `specs/ui.md` — the one page Luis uses, copy rules, colors
5. `specs/seed-and-evals.md` — seed scenarios and eval cases
6. `specs/policies.md` — the credit union policy documents (seeded verbatim)
7. `specs/tasks.md` — phased plan. Work phase by phase.

## Working with Camila (human in the loop) — highest priority
Camila reviews everything before you continue. These rules override any urge to keep going.

1. **Before each phase:** post a short plan (≤ 10 lines: files you'll create/change,
   approach, anything you're unsure about) and **wait for "OK"**.
2. **After each phase:** post the phase report (format below) and **wait for approval**.
   Do not start the next phase, and do not commit, until Camila approves.
3. **When you need something only Camila can do or provide** (API keys, accounts, a
   Railway setting, a decision, a manual check in the browser), stop immediately and post a
   `USER ACTION REQUIRED` block. Never work around a missing key with fakes or placeholders
   that hide the gap.
4. **Never paste or ask Camila to paste secrets into the chat.** Secrets go in `.env`
   (local) or Railway variables. You only need to know the variable name and that it's set.
5. **Ask before any action that costs money, touches the outside world or is hard to undo:**
   real Jev/Anthropic calls (first run, `make evals`, `--record`), `git push`, creating or
   changing anything in Railway or GitHub, deleting files you didn't create, dropping data.
6. Commit only after approval, one commit per phase, message referencing the R-/BR- IDs.

### `USER ACTION REQUIRED` block format
```
USER ACTION REQUIRED
What:   <one line>
Why:    <what it unblocks>
Steps:  1. … 2. … 3. …   (exact clicks/commands, links to the right console page)
Where:  <file or Railway variable name — never the secret value in chat>
Done when: <how Camila confirms, e.g. "reply 'done'" or "run make health">
```

### Phase report format
```
PHASE Px — <name>: DONE
Built:      <bullets: files/modules>
Covers:     <R-/BR- IDs>
Checks:     make check → pass/fail (paste the summary)
Security:   checklist items that applied this phase and how they were handled
Tests:      <n passed / n failed>
How to see it yourself: <commands or URLs to try>
Deviations / open questions: <or "none">
Next phase: <name> — waiting for your OK
```

## Working rules
- **Spec-driven.** Every module, test and commit references the R-/BR- IDs it implements.
- **If a spec is ambiguous or contradicts another spec, STOP and ask.** Do not guess
  business behavior. Technical details not covered by the spec (helper names, file splits)
  are your call — keep them simple.
- **Stop at the end of every phase** in `tasks.md`: run all checks, report what was done,
  what was tested, and any deviations. Wait for approval before the next phase.
- **No over-engineering.** No extra services, queues, caches or abstractions the specs don't
  ask for. One Postgres. One backend. One frontend.
- **Verify library and platform APIs before using them.** LangGraph, Anthropic SDK,
  Tailwind, TanStack and Railway change often: check current docs (Context7 MCP if
  available; Railway: https://docs.railway.com) instead of relying on memory.
  For Jev, the contract in `design.md §6` comes from https://docs.typesafe.ai/api
  (index: https://docs.typesafe.ai/llms.txt).
- **Tests first for business rules** (`BR-xx`): write the failing test from the spec table,
  then the code.
- **The LLM never decides money.** Rules engine (pure Python) decides; LLMs/Jev only
  understand text and write text. Refund amount always comes from the ledger.

## Stack (fixed — do not swap)
- Backend: Python 3.12, uv, FastAPI, Pydantic v2, SQLAlchemy 2 (async, asyncpg), Alembic,
  LangGraph, Anthropic Python SDK (AsyncAnthropic), httpx (Jev), structlog, slowapi, tenacity
- DB: PostgreSQL 16 (full-text search for policy retrieval; no vector DB)
- Frontend: Vite + React + TypeScript (strict), Tailwind CSS, TanStack Query,
  @microsoft/fetch-event-source (SSE over POST), Radix primitives, motion, lucide-react
- Tests: pytest (+ pytest-asyncio), Vitest, Playwright (last phase)
- Quality: pre-commit with ruff (lint + format), mypy (strict on `backend/app`), ESLint,
  Prettier. GitHub Actions runs all of them plus tests.
- Packaging: `docker compose up` runs everything locally.
- Deployment: **Railway** (design §11): one Railway project with Postgres and one `app`
  service built from the root `Dockerfile`; FastAPI serves the API and the built frontend
  (one origin, no nginx).

## Models
| Use | Model | Env var |
|---|---|---|
| Typed decisions (intent, injection, language, tone, which fee, which policy passage) | Jev `jev-latest` | `JEV_MODEL` |
| Fallback for typed decisions when Jev fails | `claude-haiku-4-5-20251001` | `ANTHROPIC_FAST_MODEL` |
| Writing the reply to the member | `claude-sonnet-5-5` | `ANTHROPIC_WRITER_MODEL` |

## Commands (keep these working; document in README)
- `docker compose up` — db, migrations + seed, app (API + built frontend)
- `npm run dev` in `frontend/` — Vite dev server, `/api` proxied to the app
- `make check` — ruff, mypy, eslint, prettier, tests
- `make evals` — runs `evals/run_evals.py`, prints pass rate and cost
- `make test` — pytest + vitest

## Engineering practices
Clean, readable code a reviewer understands at a glance. Pragmatic, not ceremonial:
these rules exist to keep the code simple, never to add layers.

**Structure and responsibilities**
- **Single responsibility** per module, class and function. Layers have one job each and
  depend only downward:
  `api/` (HTTP: validation, status codes, serialization — no business logic, no SQL) →
  `services/` (use cases and transactions: decision, refund, audit) →
  `rules/` (pure business logic, no I/O) · `agents/` (flow orchestration, model calls) ·
  `tools/` (read-only queries) → `db/` (models, sessions, repositories).
- Dependencies are passed in (FastAPI `Depends`, constructor/function arguments), not
  imported globals, so units can be tested with fakes. No service locators, no DI
  frameworks.
- No abstraction without a second real use. A Protocol is fine where there are already
  two implementations (e.g. `Decider`: Jev and Haiku). No base classes "for later".
- Frontend: components render; hooks fetch/mutate (TanStack Query); pure helpers format
  and decide (money, dates, which action is available). No API calls inside presentational
  components.

**Code style**
- Small functions (aim ≤ 30 lines), early returns, no deep nesting, no flags that change
  what a function does (split it instead).
- Intention-revealing names in the domain language of the specs (`fee`, `refunds_left`,
  `tier`), no abbreviations, no `data`/`info`/`utils` dumping grounds.
- Full type hints (mypy strict) and TypeScript strict; no `Any`/`any` without a comment
  explaining why. Pydantic models at every boundary (API, tools, model answers).
- Constants and thresholds from config, never magic numbers in logic.
- Errors: domain exceptions (`CaseAlreadyDecided`, `ApprovalNotAllowed`,
  `FeeAlreadyRefunded`, `ModelUnavailable`) raised in services, mapped to HTTP/plain text
  in one place in `api/`. Never swallow exceptions silently; never `except Exception: pass`.
- Comments explain *why* (and reference R-/BR- IDs), not *what*. No dead code, no
  commented-out code.
- Tests follow Arrange–Act–Assert, one behavior per test, named after the behavior
  (`test_staff_cannot_override_limit_reached`).

## Security checklist (apply where relevant; review it in every phase report)
- **Input:** validate every request with Pydantic (types, ranges, lengths, enums); reject
  unknown fields on write endpoints; limit request body size.
- **SQL:** ORM or bound parameters only. Never build SQL with f-strings or string
  concatenation (including FTS queries: pass the user/agent text as a parameter to
  `websearch_to_tsquery`).
- **Least privilege:** `agent_ro` for tools; `app_rw` for services; the admin DB URL only
  in the roles bootstrap. Containers run as a non-root user.
- **Secrets:** env vars only; never logged, never returned by the API, never in error
  messages; `.env` git-ignored; add a pre-commit secret scan (e.g. `detect-secrets` or
  `gitleaks`).
- **Money integrity:** refund amount from the ledger only (BR-10); idempotency keys and DB
  unique constraints (R-15); row lock on the case during a decision.
- **Prompt injection:** member text is always data (delimited, never in system prompts);
  models have no write tools; output guard before anything is saved (design §7.5).
- **HTTP:** one origin (FastAPI serves the SPA), so no CORS in production; security
  headers from a FastAPI middleware (`Content-Security-Policy`, `X-Content-Type-Options`,
  `Referrer-Policy`, `X-Frame-Options: DENY`, HSTS in production); rate limits (R-22) on
  `/api/*` only; FastAPI `/docs` disabled when `APP_ENV=production`.
- **Errors:** friendly messages to clients, details only in logs (without personal data);
  no stack traces in responses.
- **Dependencies:** pin versions (`uv.lock`, `package-lock.json`); CI runs `pip-audit`
  and `npm audit --audit-level=high` (report findings, don't block on low severity).
- **Frontend:** never use `dangerouslySetInnerHTML`; render member text as plain text.

## OWASP coverage (R-40)
Use these two lists as the security review frame. Each phase report's "Security:" line
names the items it touched. The README ends with this mapping (with links to the code).

### OWASP Top 10:2025 (web application)
| ID | Risk | How this app handles it |
|---|---|---|
| A01 | Broken Access Control | Login required (design §4.0); actor from session only; BR-09 enforced server-side in `DecisionService`; `agent_ro` cannot write; deny by default (routers require auth unless explicitly public) |
| A02 | Security Misconfiguration | `/docs` off in production; no CORS in production (one origin: FastAPI serves the SPA); security headers + CSP from a FastAPI middleware (HSTS in production); unknown `/api/*` → JSON 404, never the SPA; no default passwords (seed passwords from env, startup fails if empty in production); non-root container; debug off |
| A03 | Software Supply Chain Failures | Pinned lockfiles (`uv.lock`, `package-lock.json`); `pip-audit` + `npm audit` in CI; pinned base images (no `latest`); minimal dependencies; Dependabot config |
| A04 | Cryptographic Failures | argon2id password hashes; signed session cookie with a strong secret; TLS by Railway (HTTPS only, `Secure` cookies, HSTS header); DB connections over SSL in production |
| A05 | Injection | ORM / bound parameters only (incl. FTS); Pydantic validation; React escaping, no `dangerouslySetInnerHTML`; prompt injection handled per LLM01 below |
| A06 | Insecure Design | Rules engine owns money decisions; one explicit refund action; tiered autonomy with limits; idempotency + unique constraints; threat cases in evals (E30–E32) |
| A07 | Authentication Failures | Login throttling, generic errors (no user enumeration), session regeneration on login, HttpOnly/SameSite=Strict cookies, 8 h expiry, logout clears session |
| A08 | Software or Data Integrity Failures | Idempotency keys; row lock + version check; DB constraints for refunds; CI must pass before Railway deploys ("Wait for CI"); seed never overwrites a non-empty production DB |
| A09 | Security Logging & Alerting Failures | Audit log (who/when/what/why) for logins, decisions, refunds, injection detections; structured logs with request id, no PII; 4xx/5xx and injection counts visible in logs |
| A10 | Mishandling of Exceptional Conditions | Every external call has timeout + bounded retries; failures route to manual review (never "approve by default" — fail closed); one global error handler; transactions roll back fully on error |

### OWASP Top 10 for LLM Applications 2025
| ID | Risk | How this app handles it |
|---|---|---|
| LLM01 | Prompt Injection | Jev injection check before anything else; member text only as delimited data; models have no tools that write; output guard; evals E30–E32 |
| LLM02 | Sensitive Information Disclosure | Minimal data per prompt (design §8); no IDs/account numbers to models; masked logs |
| LLM03 | Supply Chain | Official SDK/API endpoints only; pinned SDK versions |
| LLM04 | Data and Model Poisoning | Feedback evals are reviewed before being added to the eval set (exported as files, not auto-trusted); policies are seeded from versioned files |
| LLM05 | Improper Output Handling | Model output never executed or used as SQL/HTML; draft rendered as plain text; output guard validates amounts/terms; typed answers validated with Pydantic |
| LLM06 | Excessive Agency | Agents read only; the refund is one explicit service call gated by rules and tiers; amount from ledger (BR-10) |
| LLM07 | System Prompt Leakage | No secrets or business thresholds in prompts; guard blocks prompt-like text in drafts |
| LLM08 | Vector and Embedding Weaknesses | Not applicable (no vectors; FTS over trusted, seeded policies) — say so in the README |
| LLM09 | Misinformation | Policy quotes are verbatim passages, never generated; draft limited to `<case_facts>`; checks shown to Luis are produced by code |
| LLM10 | Unbounded Consumption | Rate limits, run cap per case, `max_tokens`, timeouts, message truncation (R-41), cost per run tracked |

## Hard rules (security / privacy)
- Secrets only from environment variables. `.env` is git-ignored; `.env.example` is complete.
- Agent tools use the **read-only DB user** (`agent_ro`). Only services in
  `backend/app/services/` write, using `app_rw`.
- No message bodies, names, or full account numbers in logs. Mask account numbers as `••4210`.
- Prompts receive only what the step needs (see `design.md §8`). Never send member_id,
  account numbers or transaction IDs to an LLM or to Jev.
- The UI never shows stack traces, internal IDs, model names or raw probabilities.

## Definition of done (every phase)
- `make check` passes; new code has tests where the phase asks for them.
- Behavior matches the referenced R-/BR- IDs.
- No TODOs left without a note in the phase report.
