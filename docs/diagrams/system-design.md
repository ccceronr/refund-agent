# System design

```mermaid
flowchart LR
  user["Luis / Marta<br/>(browser)"] -->|"HTTPS · one origin<br/>SPA + /api (SSE for runs)"| edge["Railway edge<br/>TLS · X-Real-IP"]
  edge --> app

  subgraph railway["Railway project · production"]
    app["<b>app</b> service<br/>FastAPI: /api + built React SPA<br/>LangGraph flow · rules engine · services"]
    pg[("<b>Postgres</b><br/>private network · ssl=require")]
    app -->|"app_rw: services write<br/>(refunds, decisions, audit)"| pg
    app -->|"agent_ro: tools read<br/>(SELECT only)"| pg
  end

  app -->|"typed decisions<br/>(intent, injection, fee, policy, guard)"| jev["TypeSafe API<br/>Jev"]
  app -->|"fallback decisions · reply writer"| claude["Anthropic API<br/>Haiku 4.5 · Sonnet 5.5"]

  gh["GitHub<br/>main"] --> ci["GitHub Actions CI<br/>lint · types · tests · offline evals<br/>audits · gitleaks · image build"]
  ci -->|"Wait for CI"| deploy["Railway deploy<br/>pre-deploy: alembic upgrade + seed --if-empty<br/>health check /api/health"]
  deploy --> app
```

- **One service, one origin**: FastAPI serves the API and the SPA; no nginx, no CORS.
- **Money moves in one place** (`RefundService`), as `app_rw`; the agent's tools can only read
  (`agent_ro`). The database is reachable only on Railway's private network.
- **Secrets** live in Railway variables; the app never holds the Postgres superuser URL
  (the roles bootstrap runs once from a laptop, `docs/deploy-railway.md`).

## At scale (not built)

The same container on **AWS ECS Fargate** behind an **ALB** and **CloudFront** (caching
`/assets/*`), **RDS for PostgreSQL Multi-AZ**, **Secrets Manager** for the variables,
**CloudWatch** for the JSON logs and alarms, and **Amazon Bedrock** as an alternative
Claude endpoint. The agent would run when each message arrives (a queue of new
conversations) instead of when Luis opens a case.

![System design](system-design.png)
