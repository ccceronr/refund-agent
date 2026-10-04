# Deploying to Railway

One Railway project, environment `production`, two services: **Postgres** (Railway's
database) and **app** (built from the root `Dockerfile`; FastAPI serves the API and the
built frontend on one origin). Design: `specs/design.md` §11 and §3.3.

Nothing secret is ever pasted in chat, committed, or typed on a command line that ends up
in shell history: secrets go from a generator (or the clipboard) straight into Railway.

## 0. Before you start

- A Railway account and the CLI: `npm i -g @railway/cli` (or `brew install railway`),
  then `railway login`.
- The GitHub repository exists and `main` is pushed (CI green).
- `uv` installed locally (for the one-time roles bootstrap in step 4).
- New API keys for Anthropic and TypeSafe (Jev): rotate the local ones first.

## 1. Project, database and app service

1. Railway dashboard → **New Project** → **Deploy from GitHub repo** → pick this repo.
   Rename the created service to `app`. Root directory: the repo root (default).
   The first build may fail until the variables exist: that's expected.
2. In the project: **+ New** → **Database** → **PostgreSQL**. Keep the service name
   `Postgres` (the variables below reference it by name). Railway's template is
   PostgreSQL **18**; compose and CI use 16. Production runs on 18 (design §11).
3. `app` → **Settings** → **Deploy**, set these by hand (the dashboard is the only source
   of these settings; see "What we learned" below):
   - **Pre-deploy command**: `sh bin/pre-deploy.sh`
   - **Healthcheck path**: `/api/health`, timeout `120`
   - **Restart policy**: On failure, max retries `3`
4. In a terminal at the repo root: `railway link` → this project, environment
   `production`, service `app`.

## 2. Variables of the `app` service

Set them in the dashboard (`app` → **Variables** → **Raw Editor** works) or with the CLI.
`--skip-deploys` avoids one deploy per variable.

Generated secrets (random, URL-safe, never shown):

```bash
openssl rand -hex 32 | railway variable set APP_RW_PASSWORD --stdin --service app --skip-deploys
openssl rand -hex 32 | railway variable set AGENT_RO_PASSWORD --stdin --service app --skip-deploys
openssl rand -hex 48 | railway variable set SESSION_SECRET --stdin --service app --skip-deploys
openssl rand -base64 18 | railway variable set SEED_PASSWORD_LUIS --stdin --service app --skip-deploys
openssl rand -base64 18 | railway variable set SEED_PASSWORD_MARTA --stdin --service app --skip-deploys
```

API keys (paste the key, then Enter and Ctrl-D; it stays on your machine and in Railway):

```bash
railway variable set ANTHROPIC_API_KEY --stdin --service app --skip-deploys
railway variable set JEV_API_KEY --stdin --service app --skip-deploys
```

Plain values and references (these hold no secret themselves):

| Variable | Value |
|---|---|
| `APP_ENV` | `production` |
| `DATABASE_URL_RW` | `postgresql+asyncpg://app_rw:${{ APP_RW_PASSWORD }}@${{Postgres.PGHOST}}:${{Postgres.PGPORT}}/${{Postgres.PGDATABASE}}?ssl=require` |
| `DATABASE_URL_RO` | `postgresql+asyncpg://agent_ro:${{ AGENT_RO_PASSWORD }}@${{Postgres.PGHOST}}:${{Postgres.PGPORT}}/${{Postgres.PGDATABASE}}?ssl=require` |
| `LOCAL_TIMEZONE` | optional, default `America/Chicago` |

Everything else in `.env.example` has a sensible default. Never set on `app`:
`DATABASE_ADMIN_URL`, `POSTGRES_PASSWORD`, `FAULT_INJECTION`, `CORS_ORIGINS`.

Why each one:

| Variable | Read by | References `${{Postgres.…}}` |
|---|---|---|
| `APP_ENV` | app, seed | no |
| `DATABASE_URL_RW` | app (services), pre-deploy (migrations, seed) | yes: `PGHOST`, `PGPORT`, `PGDATABASE` |
| `DATABASE_URL_RO` | app (agent tools, read-only) | yes: `PGHOST`, `PGPORT`, `PGDATABASE` |
| `APP_RW_PASSWORD`, `AGENT_RO_PASSWORD` | the two URLs above; the one-time bootstrap | no |
| `SESSION_SECRET` | app (signed session cookie) | no |
| `SEED_PASSWORD_LUIS`, `SEED_PASSWORD_MARTA` | pre-deploy seed (stores argon2id hashes) | no |
| `ANTHROPIC_API_KEY`, `JEV_API_KEY` | app (models) | no |

Railway cannot scope a variable to the pre-deploy step only, so the seed passwords are
also visible to the app process, which never reads them.

## 3. Turn on "Wait for CI"

`app` → **Settings** → **Source** → enable **Wait for CI**: a push to `main` deploys only
after GitHub Actions passes (OWASP A08).

## 4. Roles bootstrap, once, from your machine

The app connects as `app_rw` and `agent_ro`; they must exist before the first deploy.
This step uses the Postgres superuser through Railway's public endpoint, from your
machine only. The app service never holds that URL (design §3.3).

1. `Postgres` → **Settings** → **Networking** → **Public Access** (formerly "TCP Proxy")
   → enable it. Only while it is on does the service have `DATABASE_PUBLIC_URL`.
2. Press **Deploy** on the Postgres service if the dashboard shows staged changes.
3. Run the bootstrap:

```bash
export DATABASE_ADMIN_URL="$(railway variable list --service Postgres --kv | sed -n 's/^DATABASE_PUBLIC_URL=//p')"
railway run --service app -- uv run --project backend python -m app.db.bootstrap_roles
unset DATABASE_ADMIN_URL
```

It logs `roles_bootstrapped` on success. Run it again only if you change a role password
(then redeploy). If it fails because the user cannot create roles, stop and send the
error line (no secrets).

4. **Turn Public Access off again** (and Deploy the staged change). The database is then
   reachable only from inside the project, over the private network.

## 5. Deploy and domain

1. Deploy: `app` → **Deployments** → **Deploy** (redeploys the latest commit of `main`;
   from then on every push to `main` deploys on its own once CI is green). Avoid
   `railway up`: it uploads the local folder instead of the reviewed commit.
   The pre-deploy runs `alembic upgrade head` and `seed --if-empty` as `app_rw`.
2. `app` → **Settings** → **Networking** → **Generate Domain** (target port: the one the
   app listens on, `$PORT`).

## 6. Check it

The pre-deploy must have run before the app started: the deployment logs show
`Running upgrade` (alembic) and `seed_loaded` or `seed_skipped` before `Started server
process`, and no `run_recovery_failed`. The active deployment's settings:

```bash
railway status --json | grep -o '"preDeployCommand":[^,]*' | sort -u   # not null
```

Replace `<domain>` with the generated one.

```bash
curl -fsS https://<domain>/api/health                       # {"status":"ok","db":"ok",...}
curl -sI https://<domain>/ | grep -iE 'strict-transport|content-security|x-frame'
curl -s https://<domain>/api/does-not-exist                 # JSON 404, not the page
```

Then in the browser: sign in as `luis` (password: `railway variable list --service app --kv`
on your machine, never in chat), open a case and let it prepare, and check the `app` logs
(JSON lines with a `request_id`, no names or message text).

Checked on production (2026-10-03): `Strict-Transport-Security`, `Content-Security-Policy`,
`X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`; http → https (301); unknown
`/api/...` → JSON 404; `/docs` and `/openapi.json` → 404; no session → 401; a change without
`X-Requested-With` → 403; session cookie `Secure; HttpOnly; SameSite=Strict; Max-Age=28800`;
`app` has no `DATABASE_ADMIN_URL`/`POSTGRES_PASSWORD`; database URLs use the private host
with `?ssl=require`; Postgres has no public endpoint; logs carry `request_id` and no names,
message text or account numbers (variable names only: `railway variable list --kv | cut -d= -f1`).

## 7. Reset the demo data (before recording or sending)

A one-time, audited reload of the seed, run by the pre-deploy inside Railway as `app_rw`
(no admin URL, no Public Access, nothing in the app). The confirmation is the app's
domain and **today's date in UTC**:

```bash
railway variable set "DEMO_RESET=app-production-6228.up.railway.app@$(date -u +%F)" --service app
```

Then press **Deploy**. The deployment logs show `demo_reset` with `outcome: reset`; the
queue is back to the 22 new cases (the audit log keeps its history plus a `demo_reset`
entry). A wrong domain or another day's date fails the pre-deploy and deletes nothing.
The same value never resets twice (later deploys log `already_done`); delete the variable
when done: `railway variable delete DEMO_RESET --service app`.

## What we learned

- **SSH from WSL did not work.** `railway ssh` (and the SSH tunnel) needs an SSH key
  Railway can use without a prompt; a passphrase-protected key fails in WSL (no
  `ssh-askpass`). Use Public Access for the one-time bootstrap instead, then close it.
- **"TCP Proxy" is now "Public Access"** (Postgres → Settings → Networking). It was opened
  only for the roles bootstrap and closed right after.
- **Dashboard changes are staged.** Variables and settings apply only after pressing
  **Deploy** on the banner; until then the running deployment keeps the old values.
- **`railway.toml` took over the deploy settings without applying them.** The deployment
  recorded those fields as coming from the file (`propertyFileMapping.deploy.preDeployCommand
  = $.deploy.preDeployCommand`), yet its manifest showed `preDeployCommand: null`,
  `healthcheckPath: null` and the default restart retries, and the values set by hand in
  the dashboard were ignored too. Its format was valid (array form, schema-checked; the
  plain-string `healthcheckPath` was dropped as well). So the app started twice before the
  tables existed (`relation "agent_runs" does not exist`, `run_recovery_failed`). The file
  was removed; the dashboard now holds the pre-deploy, health check and restart policy
  (step 1.3), and the Dockerfile is still picked up on its own. Railway marks Config as
  Code as deprecated in favour of Infrastructure as Code (`.railway/railway.ts`).
- **How the tables first appeared is not explained.** The app's startup errors show they
  did not exist at 02:24 and 02:29 UTC, and nobody ran migrations by hand; with the
  pre-deploy active this no longer matters.
- **PostgreSQL 18 by default.** Railway's template ships 18 and production stays on 18 (a
  documented deviation from the stack's 16; design §11). Checked locally on 18: roles
  bootstrap, migrations, seed and startup recovery all work.
