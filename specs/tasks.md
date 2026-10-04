# Tasks

Deadline: **Sunday 2026-10-04, 23:59 (America/Bogota)**. Work phase by phase.

**Every phase follows the same loop** (see CLAUDE.md "Working with Camila"):
1. Post a short plan → wait for "OK".
2. Build. If you need something from Camila, stop and post `USER ACTION REQUIRED`.
3. Run `make check`, post the phase report → wait for approval.
4. After approval: commit (one commit per phase, IDs in the message). Push only if Camila
   says so.

Each phase lists **👤 Camila** — the actions only Camila can do. Raise each one as a
`USER ACTION REQUIRED` block at the moment you need it, not before.

Time boxes are guidance. If a phase runs > 50% over, stop and say so.

---

## P0 — Scaffold and quality gates (~1.5 h)
- Repo layout from design §2. `uv` project in `backend/`, Vite React TS in `frontend/`
  (Vite dev server proxies `/api` to the app for frontend development).
- Tooling: ruff (lint+format), mypy strict on `backend/app`, ESLint, Prettier,
  `.pre-commit-config.yaml`, `Makefile` (`check`, `test`, `evals`, `fmt`, `health`).
- One root `Dockerfile` (multi-stage: Node builds `frontend/` → `dist/` copied to
  `backend/app/static/`; Python runtime, non-root, reads `$PORT`), used by both compose and
  Railway (design §11). `backend/app/static/` is git-ignored, never committed.
- `docker-compose.yml`: `db` (postgres:16, healthcheck), `migrate` (bootstrap roles +
  alembic upgrade, runs once; the seed joins in P1), `app` (depends on migrate; serves
  `/api` and the SPA).
- `.env.example` complete (design §10). `core/config.py` (pydantic-settings).
- `app.db.bootstrap_roles` (design §3.3): creates/updates `app_rw` and `agent_ro`
  (passwords from env, `statement_timeout`). Table grants come with the P1 migration.
- `GET /api/health` with DB check. structlog + request id middleware. SPA serving per
  design §1 "Serving": `/assets/*` long cache, `index.html` fallback without cache,
  unknown `/api/*` → JSON 404.
- GitHub Actions `ci.yml`: backend (ruff, mypy, pytest with a postgres service,
  pip-audit), frontend (eslint, prettier --check, tsc, vitest, npm audit).
- Security baseline (CLAUDE.md checklist): non-root container, secret scan in
  pre-commit, security headers middleware (CSP, `X-Frame-Options`, HSTS in production…),
  request body size limit, no CORS in production, `/docs` off in production, layer
  folders created so responsibilities are clear from day one.
**👤 Camila:** create the empty GitHub repo and give you its URL (or confirm it's local
only for now); install Docker Desktop if missing; copy `.env.example` to `.env` and
choose the local DB passwords (`POSTGRES_PASSWORD`, `APP_RW_PASSWORD`,
`AGENT_RO_PASSWORD`).
**Done when:** `docker compose up` serves a blank page on the app port, `/api/health` →
ok, an unknown `/api/...` path → JSON 404, and `npm run dev` in `frontend/` shows the
page with `/api` proxied. CI file valid.
**Covers:** R-32, R-34 (logging part), R-36, R-37. **→ STOP**

## P1 — Database, roles and seed (~2.5 h)
- SQLAlchemy models for given + added tables (design §3). Alembic migration.
- `agent_ro` grants and default privileges in the migration (design §3.3; the roles
  themselves exist since P0). Two engines/sessions (`app_rw`, `agent_ro`).
- Seed: PDF rows verbatim + scenarios (seed-and-evals §2) + policies (policies.md, split
  into passages) + staff + profiles + credit unions + cases (`new`).
  `--if-empty` flag for Railway redeploys; `--reset` for local.
- Seed invariants asserted.
**Tests:** seed invariants; `agent_ro` cannot INSERT/UPDATE (expect permission error).
**Done when:** fresh `docker compose up` creates everything; re-running seed is safe.
**Covers:** R-30, R-31. **→ STOP**

## P2 — Read-only tools (~2 h)
`backend/app/tools/` (all use `agent_ro`, return Pydantic models, `Decimal` money):
`load_case`, `get_member_accounts`, `find_fee_candidates`, `get_day_postings`
(posting order from `posting_ref`), `get_refund_history`, `get_member_standing`,
`search_policy` (FTS). Each tool call is timed and recorded as a step (design §9) by a
small wrapper.
**Tests (pytest against the seeded DB):** Ana's day postings come in order 0000, 0005,
0010; Ana's refund history = 2 (across sub-accounts); candidates for 5023 = 2; standing
for 316/317/318; FTS returns the refund-limit passage for its query.
**Covers:** R-07, R-10 (retrieval), R-31, R-34. **→ STOP**

## P3 — Rules engine (~2 h) — tests first
`backend/app/rules/`: fee classification, BR-01…BR-10 as pure functions, `evaluate()`
returning recommendation, reason code, all checks (with plain texts), tier, refunds left.
Check texts and manual-reason texts (BR-13) generated here from templates.
**Tests:** one test per row of the BR-07 and BR-08 tables, BR-02 examples (Ana, 5017,
5018), BR-03 window edges (exactly 365 days), BR-04 edge (exactly 60 days), BR-09 matrix,
AUTO conditions each failing alone.
**Covers:** BR-01…BR-10, BR-13. **→ STOP**

## P4 — Model clients (~2 h)
- `agents/decider.py`: Jev httpx client (design §6), typed answer models, retries,
  timeout, usage → step. Haiku fallback (design §6.2). `FAULT_INJECTION` support.
- `agents/writer.py`: Sonnet writer (design §7.1) with prompt caching; templates
  (`agents/templates.py`, design §7.2).
- `agents/guard.py`: output guard (design §7.5).
- `core/pricing.py` + `pricing.toml` (fill from official pricing pages; note the date).
- `make smoke-models`: one tiny real call to Jev and one to each Claude model.
**👤 Camila:** put `JEV_API_KEY` and `ANTHROPIC_API_KEY` in `.env`; approve running
`make smoke-models` (first real, paid calls). If you can't find a price on the official
pages, ask Camila instead of guessing.
**Tests:** decider parses each answer type (recorded JSON fixtures); fallback used when
Jev returns 529 three times (mock transport); guard catches wrong amount, banned term,
long digit run; templates exist for every outcome × language. Unit tests never call real
APIs.
**Covers:** R-04 (client), R-11, R-12, R-18, R-19, R-33. **→ STOP**
**Pending (2026-10-03):** `make smoke-models` not run yet (no API keys). It runs together
with the P5 real runs in one command once the keys are in `.env` (see the P5 report).

## P5 — Agent graph (~3 h)
- LangGraph graph per design §5 with conditional edges, parallel evidence gathering,
  whole-run timeout, step persistence, SSE event emission via an async queue.
- `finalize`: saves proposal + case status; AUTO → `RefundService.execute` (P6 service,
  build it here if needed) + reply message + close.
- Startup hook: runs left `running` → failed / `TIMEOUT`.
- A CLI to run one case: `python -m app.agents.run_case 5012 --dry-run`.
**👤 Camila:** approve the real runs of 5012, 5013 and 5022 (dry-run, paid calls) and
review their output.
**Tests:** graph routing with the decider/writer mocked: injection → manual; other intent →
not_refund; 0/1/many candidates; writer failure → template; timeout → manual.
**Covers:** R-04…R-13, R-20, R-30. **→ STOP** (show the CLI output for 5012, 5013, 5022)
**Pending (2026-10-03):** built and tested with mocks only (no API keys yet). `make real-runs`
runs the P4 smoke test and the three dry runs together once the keys are in `.env`.

## P6 — API, decisions and refunds (~3 h)
- Routers per design §4: `/health`, `/cases`, `/cases/{id}`, `/cases/{id}/run` (SSE +
  JSON), `/cases/{id}/decision`, `/auth/*` (design §4.0). Error handler → friendly JSON. slowapi limits
  (client IP from `X-Real-IP` set by Railway's edge, design §11).
  Input validation (Pydantic, path ids positive ints, Idempotency-Key UUID).
- `DecisionService` (BR-09, BR-12, idempotency, row lock), `RefundService` (BR-11),
  `AuditService` (R-35), feedback eval recording (R-23).
**Tests:** **API test:** approve 5012 twice with the same key → one refund, same response;
different key → 409; staff approving a LIMIT_REACHED override → 403; supervisor → 200.
Unit: RefundService refuses an already-refunded fee.
Auth: no session → 401 on every protected endpoint; wrong password → generic message;
6th failed login → 429; mutating request without `X-Requested-With` → 403; the actor
recorded in `decisions` is the session user even if the body tries to set another.
**👤 Camila:** set `SESSION_SECRET`, `SEED_PASSWORD_LUIS`, `SEED_PASSWORD_MARTA` in `.env`.
**👤 Camila:** try the endpoints yourself with the commands in the report (curl examples
or `/docs`).
**Covers:** R-01, R-02, R-14, R-15, R-21, R-22, R-23, R-35, BR-09, BR-11, BR-12. **→ STOP**

## P7 — Frontend (~5 h)
Read `ui.md` fully first. Use the `frontend-design` skill if available.
- Layout, queue, case page, recommendation card, evidence, reply editor, action bar,
  reject dialog, run progress (SSE), sign-in screen and sign-out, friendly errors,
  empty states.
- Vitest per ui.md §4.
- Split it in two checkpoints: **P7a** static layout with real data (no actions) → STOP
  for a design review; **P7b** actions, streaming, errors → STOP.
**👤 Camila:** review the design in the browser at each checkpoint and walk the demo path.
**Done when:** the full demo path works in the browser: open 5013 (streams, auto
refunds), open 5012 (approve in one click), open 5015 as Luis (no refund; sign in as
Marta → override possible), open 5022 (manual review with reason).
**Covers:** R-01…R-03, R-16, R-17, ui.md. **→ STOP** (screenshots)

## P8 — Evals and cost report (~2 h)
`evals/cases/*.json` (seed-and-evals §3), `run_evals.py` with `--offline/--record/--case`,
`export_feedback.py`. Record fixtures once with real keys so CI runs offline.
**👤 Camila:** approve the full real eval run and `--record` (≈ 25 cases × paid calls;
give a cost estimate first).
**Done when:** `make evals` prints the report; pass rate ≥ 90 %. Report failures
honestly; fix the prompts/questions, never the expected values (unless the spec is wrong —
then ask).
**Covers:** R-23, R-24. **→ STOP** (paste the report)

## P9 — Deploy to Railway (~2 h)
Read design §11 and the current Railway docs first.
- (Done in the dashboard, not `railway.toml`; see design §11.) Deploy settings for the single `app` service (build from the root `Dockerfile`,
  health check `/api/health`, pre-deploy command `alembic upgrade head` + `seed
  --if-empty` as `app_rw`, restart policy). No roles bootstrap in the deploy (design §3.3).
- `docs/deploy-railway.md`: the exact steps Camila follows, and the full list of variables
  for the `app` service (names only) with which ones reference `${{Postgres.…}}`.
- Verify after deploy: the `app` service has no `DATABASE_ADMIN_URL`/`POSTGRES_PASSWORD`,
  `/api/health` ok on the public URL, the SPA loads with the
  security headers (HSTS included), an unknown `/api/...` path → JSON 404, queue loads,
  one case runs end to end, logs show request ids and no personal data.
**👤 Camila** (all in the Railway dashboard or CLI, guided step by step):
create the Railway project and connect the GitHub repo; add the Postgres database;
create the `app` service (root directory = repo root); run the roles bootstrap once from
your machine with `railway run` (exact command in `docs/deploy-railway.md`); set the
variables (no admin URL on the app service); generate the public domain; turn on
"Wait for CI"; push to `main` when told.
Send you any failing build/deploy log (paste the log, never secrets).
**Done when:** the public URL serves the app and `<app-domain>/api/health` → ok.
**Covers:** Deployment bonus, R-36 in the cloud. **→ STOP**

## P10 — Delivery (~2 h)
- `README.md`: what it does (3 lines), live URL, one-command local run, env vars, demo
  walkthrough (the P7 path), architecture summary + links to diagrams, decisions and
  trade-offs (tiered autonomy, rules over LLM, Jev usage, read-only agents, FTS over
  vectors), how to run tests and evals, eval results, what I'd do next.
  Known limitations to state: the seed has no original fee rows for prior refunds (like the
  PDF); with full history, `identify_fee` should prefer fees that are not yet refunded.
  In production the agent runs when each message arrives (the demo prepares new cases on
  open or with "Prepare new messages", R-03). Login throttling lives in memory (one
  process); session cookies can't be revoked server-side before they expire (SSO in
  production).
  Under A02: the CSP stays strict (no `'unsafe-inline'` anywhere): the policy side panel
  and the reject form are non-modal components, so nothing injects inline styles.
  Deviation to state: PostgreSQL 18 in production (Railway's template; local and CI on
  16; checked on 18 locally: bootstrap, migrations, seed, recovery). Demo reset in
  production: `docs/deploy-railway.md` §7.
  Evals: show both recorded runs (`evals/reports/run-1-before-guard-fix.txt`: 24/25, 96 %;
  `run-2-after-guard-fix.txt`: the result after) and tell E15 as the example of evals
  improving the system: a correct "already refunded" denial was read as a confirmation by
  the guard's outcome question, the draft was replaced by the template, and rewording the
  question ("now", design §7.5) fixed it with no regression.
- `docs/diagrams/system-design.md`: Mermaid, one simple diagram: browser → Railway
  (`app`: FastAPI serving the API and the SPA; Postgres) → Anthropic/TypeSafe, GitHub
  Actions; plus the "at scale" note (design §1). Export PNG too.
- `docs/diagrams/agent-flow.md`: Mermaid flow (design §5, §7.4) + the prompts and Jev
  questions listed below it.
- `docs/demo-script.md`: a 90-second script for the end-to-end demo video (required
  deliverable).
- CI green. Fresh clone → `cp .env.example .env` → add keys → `docker compose up` works.
**👤 Camila:** record the demo video following the script; review the README and diagrams;
make the repo accessible to the reviewers.
**→ STOP**

## P11 — Extras, only if time remains (in this order)
1. Playwright: happy path (5012 approve) + one failure (`FAULT_INJECTION=jev_down` +
   `anthropic_down` → manual review with reason shown). Local only.
2. MCP server (design §12).
