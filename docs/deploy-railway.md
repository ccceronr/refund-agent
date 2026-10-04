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
   Railway reads `railway.toml` (Dockerfile build, pre-deploy, health check).
   The first build may fail until the variables exist: that's expected.
2. In the project: **+ New** → **Database** → **PostgreSQL**. Keep the service name
   `Postgres` (the variables below reference it by name).
3. In a terminal at the repo root: `railway link` → this project, environment
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
This step uses the Postgres superuser through Railway's public TCP proxy, from your
machine only. The app service never holds that URL (design §3.3).

```bash
export DATABASE_ADMIN_URL="$(railway variable list --service Postgres --kv | sed -n 's/^DATABASE_PUBLIC_URL=//p')"
railway run --service app -- uv run --project backend python -m app.db.bootstrap_roles
unset DATABASE_ADMIN_URL
```

It logs `roles_bootstrapped` on success. Run it again only if you change a role password
(then redeploy). If it fails because the user cannot create roles, stop and send the
error line (no secrets).

## 5. Deploy and domain

1. Deploy: `app` → **Deployments** → **Deploy** (redeploys the latest commit of `main`;
   from then on every push to `main` deploys on its own once CI is green). Avoid
   `railway up`: it uploads the local folder instead of the reviewed commit.
   The pre-deploy runs `alembic upgrade head` and `seed --if-empty` as `app_rw`.
2. `app` → **Settings** → **Networking** → **Generate Domain** (target port: the one the
   app listens on, `$PORT`).

## 6. Check it

Replace `<domain>` with the generated one.

```bash
curl -fsS https://<domain>/api/health                       # {"status":"ok","db":"ok",...}
curl -sI https://<domain>/ | grep -iE 'strict-transport|content-security|x-frame'
curl -s https://<domain>/api/does-not-exist                 # JSON 404, not the page
```

Then in the browser: sign in as `luis` (password: `railway variable list --service app --kv`
on your machine, never in chat), open a case and let it prepare, and check the `app` logs
(JSON lines with a `request_id`, no names or message text).
