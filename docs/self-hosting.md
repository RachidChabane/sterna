# Self-hosting Sterna

From `git clone` to a running instance. Two paths:

- **[Path A — Docker Compose](#path-a--docker-compose)**: one host, the whole
  stack, Cloudflare Tunnel as the only ingress. Start here. This is also the
  local development setup.
- **[Path B — Kubernetes](#path-b--kubernetes)**: kustomize manifests plus
  Terraform for a self-managed k3s cluster on Hetzner Cloud. Same images, same
  migrations, so moving from A to B is a redeploy rather than a rewrite.

Order-of-magnitude running cost: **a single VPS lands around €15–20/month**
(8 vCPU / 16 GB, plus free tiers for DNS, tunnel, email and error tracking); the
**k3s path is roughly €100–160/month** (three nodes, load balancer, managed
Postgres, paid observability). Verify current prices with the providers before
provisioning, because these numbers move. Neither figure includes LLM usage,
which is metered per request and is the dominant variable cost at any real
scale.

Nothing in this repository provisions, deploys, or bills anything on its own.
Every step that costs money is a manual action, called out below. The deploy and
Terraform workflows are `workflow_dispatch`-only; no workflow has a `schedule:`
trigger.

## Contents

- [Requirements](#requirements)
- [Path A — Docker Compose](#path-a--docker-compose)
- [External services and keys](#external-services-and-keys)
- [Path B — Kubernetes](#path-b--kubernetes)
- [Operations](#operations)

## Requirements

| | Local development | Single-host production |
|---|---|---|
| Host | macOS or Linux workstation | 1 VPS, Ubuntu LTS, 8 vCPU / 16 GB / 160 GB (the stack's memory limits total ≈ 12.9 GB, ≈ 14.2 GB with the sandbox profile) |
| Docker | Docker Desktop or Engine with the **Compose v2 plugin** (`docker compose version` prints `v2.x`) | Docker Engine + Compose v2 plugin (v2.24+) |
| Runtimes | Python 3.12+ and Node 20+ only if you run services outside Docker | not needed — everything is containerized |
| Domain / DNS | none | a domain on Cloudflare (Tunnel is the ingress) |
| Keys | an OpenRouter key is enough to chat | see [External services and keys](#external-services-and-keys) |

## Path A — Docker Compose

### 1. Local development

```bash
git clone https://github.com/RachidChabane/sterna.git
cd sterna/core
cp .env.example .env          # fill in at minimum OPENROUTER_API_KEY
make dev                      # frontend, api-gateway, web, postgres, redis, celery worker/beat, brave-search, google-maps
make migrate
make seed                     # quota tiers, preconfigured MCP servers, reference data
make createsuperuser
```

- Frontend: <http://localhost:5173>
- API: <http://localhost:8000> · Admin: `/admin` · Health: `/api/health/`

`make help` lists every target (`test`, `lint`, `coverage`, `logs`, `shell`).
Full detail, including the no-Docker path and the repository layout, is in
[`core/README.md`](../core/README.md).

The coding-agent sandbox is a **separate, optional** compose file, because its
orchestrator joins the core stack's network:

```bash
# after `make dev` has created the core_default network
cd core/sandbox
docker compose -f docker-compose.sandbox.yml up -d
```

Read the [sandbox security note](#the-sandbox-profile-read-before-enabling)
before enabling it on anything reachable from the internet.

### 2. Production on one host

Priced steps are marked 💳.

**Provision the VPS** 💳 — any provider; Ubuntu LTS, 8 vCPU / 16 GB. Allow
inbound `22/tcp` from your own IP and nothing else. The application needs **no**
open inbound ports: the Cloudflare Tunnel dials out.

**Install Docker and the Compose plugin**, then clone the repo:

```bash
git clone https://github.com/RachidChabane/sterna.git /opt/sterna
cd /opt/sterna/core
cp .env.production.example .env.production
chmod 600 .env.production
```

**Fill `.env.production`.** Every variable is documented inline and the
load-bearing ones are marked `[REQUIRED]`. `core/sterna/settings/prod.py` fails
loudly at boot on missing Resend, Turnstile and Stripe configuration, so the
`web` container crash-loops until they are set. Decide your database now:

- **Postgres in compose** (default): set `POSTGRES_PASSWORD`, leave
  `DATABASE_URL` unset. Data lives in a named volume on the host and backups are
  yours to run (step below).
- **Managed Postgres**: set `DATABASE_URL` to the provider DSN. It must support
  **pgvector**, which the knowledge base depends on.

**Build or pull images.**

```bash
# Option A — pull images published by CI
docker login ghcr.io -u <github-user>
docker compose --env-file .env.production -f docker-compose.prod.yml pull

# Option B — build on the host (~10 min, no registry account)
docker compose --env-file .env.production -f docker-compose.prod.yml build
```

`VITE_*` values are baked into the frontend bundle at **build** time, not read at
runtime. The shipped nginx config serves the SPA and proxies `/api`, `/admin`,
`/static` and `/media` to `web:8000` same-origin, so the defaults work when users
browse `app.<domain>`. If the bundle must call `api.<domain>` directly, write
`core/frontend/.env.production` before building, which forces Option B.

**Create the Cloudflare Tunnel** (dashboard → Zero Trust → Networks → Tunnels →
Create a tunnel, Cloudflared connector). Copy the token into
`CLOUDFLARE_TUNNEL_TOKEN`. Do not run Cloudflare's install command; the
`cloudflared` compose service is the connector. Add public hostnames **in this
order**, first match wins:

| Order | Hostname | Path | Service |
|---|---|---|---|
| 1 | `api.<domain>` | `ws/*` | `http://web:8000` |
| 2 | `api.<domain>` | *(empty)* | `http://api-gateway:8080` |
| 3 | `app.<domain>` | *(empty)* | `http://frontend:80` |

Row 1 exists because Channels WebSockets (`/ws/voice-rooms/…`,
`/ws/code-sessions/…`) are served by the ASGI `web` container; the gateway only
proxies REST routes and would 404 generic `/ws` paths. DNS records are created
automatically when the hostnames are saved.

**Start, migrate, seed:**

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml up -d
# wait until web / postgres / redis report healthy
docker compose --env-file .env.production -f docker-compose.prod.yml exec web python manage.py migrate --noinput
docker compose --env-file .env.production -f docker-compose.prod.yml exec web python manage.py seed_all
docker compose --env-file .env.production -f docker-compose.prod.yml exec web python manage.py createsuperuser
```

**Verify** with the smoke suite, in-container first and then against the public
URL:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml \
  exec web bash -c 'SMOKE_BASE_URL=http://web:8000 python -m pytest smoke/ -v'

cd /opt/sterna/core
SMOKE_BASE_URL=https://api.<domain> pytest -c /dev/null smoke/ -v
```

(`-c /dev/null` bypasses `core/pytest.ini`. Tests skip cleanly when optional
`SMOKE_*` variables are unset.) Then browse `https://app.<domain>` and sign in as
the superuser.

**Back up.** Single host means you are the backup team. Host cron plus
`pg_dump -Fc` piped to object storage is enough, and is deliberately the same
shape as the Kubernetes backup CronJob
(`infra-migration/kubernetes/base/backup/configmap.yaml`). Media files are
already in object storage when the `R2_*` variables are set. Test a restore once,
before you need it.

**Upgrade**: `git pull`, then pull or rebuild images, take a backup, `up -d`
(only containers whose image or config changed are recreated), then `migrate`.
Reverse migrations are not automatic, so a migration that must be undone means
restoring the dump.

### The sandbox profile, read before enabling

The coding-agent services (`orchestrator` + `egress-proxy`) sit behind
`--profile sandbox` and are **off by default**:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml \
  --profile sandbox up -d
```

The orchestrator mounts `/var/run/docker.sock` and runs as root, because that is
how it spawns sibling sandbox containers. On a single host that means **root on
the host**: a break-out from a sandbox container reaches `.env.production` and
the database. The sandbox containers themselves are hardened (read-only rootfs,
tmpfs workspace, non-root user, `internal: true` network, whitelist-only egress
through mitmproxy, and gVisor where the host provides the `runsc` runtime), but
the orchestrator's Docker socket is the boundary that a single Docker host cannot
narrow. The Kubernetes path adds a gVisor RuntimeClass, NetworkPolicies and a
separate namespace. Leave the profile off unless you need the feature, and
assume the whole host is the blast radius when you turn it on. See
[architecture.md](architecture.md#sandbox-isolation).

## External services and keys

Only the first block is required to boot and chat. Everything else degrades
gracefully: the feature is unavailable, the application still runs. All
variables live in `core/.env.example` (development) and
`core/.env.production.example` (production), documented inline.

**Required**

| Service | Variables | Why |
|---|---|---|
| OpenRouter 💳 | `OPENROUTER_API_KEY`, optionally `OPENROUTER_PROVISIONING_KEY` | All chat, tool calling and the coding agent route through it |
| PostgreSQL 16 + pgvector | `DB_*` or `DATABASE_URL` | Primary datastore and embeddings; in compose by default |
| Redis 7 | `REDIS_*`, `CELERY_BROKER_URL` | Cache, rate limits, Channels layer, Celery broker; in compose by default |
| Django secrets | `SECRET_KEY`, `JWT_SECRET_KEY`, `FIELD_ENCRYPTION_KEY`, `BYOK_ENCRYPTION_KEY` | Sessions, tokens, encryption of stored user keys |

**Production ingress and trust**

| Service | Variables | Why |
|---|---|---|
| Cloudflare Tunnel | `CLOUDFLARE_TUNNEL_TOKEN` | The only ingress in `docker-compose.prod.yml` |
| Cloudflare Turnstile | `TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY` | Signup CAPTCHA; bypassed when `DEBUG=True` |
| Resend | `RESEND_API_KEY`, `DEFAULT_FROM_EMAIL` | Verification, password reset, receipts. Verify your sending domain (SPF/DKIM/DMARC) |

**Optional, per feature**

| Feature | Service | Variables |
|---|---|---|
| Web / news / image / video search | Brave Search | `BRAVE_API_KEY` |
| Maps, directions, places | Google Maps Platform 💳 | `GOOGLE_MAPS_API_KEY` |
| Image and video generation | Google AI Studio, OpenAI, Runway | `GOOGLE_AI_STUDIO_API_KEY`, `OPENAI_API_KEY`, `RUNWAY_API_KEY` |
| Voice rooms | Deepgram (STT), ElevenLabs (TTS) | `DEEPGRAM_API_KEY`, `ELEVENLABS_API_KEY` (OpenAI TTS is the fallback) |
| Subscriptions and invoices | Stripe 💳 | `STRIPE_API_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET` |
| Social sign-in | GitHub, Google OAuth apps | `GITHUB_OAUTH_*`, `GOOGLE_OAUTH_*` — see [`operations/github-oauth-setup.md`](operations/github-oauth-setup.md) and [`operations/google-oauth-setup.md`](operations/google-oauth-setup.md) |
| MCP connectors with OAuth | Notion, Slack, Atlassian apps | `NOTION_OAUTH_*`, `SLACK_OAUTH_*`, `ATLASSIAN_OAUTH_*` |
| Object storage for media and backups | S3-compatible (Cloudflare R2) 💳 | `R2_*`, `AWS_*` |
| Error tracking | Sentry | `SENTRY_DSN` — unset means init is a no-op |

Keep Stripe in **test mode** until you actually intend to charge money. Non-production
settings refuse `sk_live_` keys at boot by design; `manage.py sanity_check_stripe_mode`
tells you which mode you are in, and `manage.py sync_stripe_prices` creates the
products and prices from the seeded tiers.

## Path B — Kubernetes

The Kubernetes artifacts build and validate in CI (`kubectl kustomize` on both
overlays, `terraform validate`, module mock tests) and the stack has run on a
managed staging cluster. It has **not** served production traffic. Budget a
first bring-up as a project.

What is in the repository:

- `infra-migration/kubernetes/base/` — one deployment per service, plus
  `namespace.yaml`, a `gvisor` RuntimeClass, NetworkPolicies, a separate
  sandboxes namespace, a backup CronJob, and External Secrets definitions.
- `infra-migration/kubernetes/overlays/{staging,production}/` — kustomize
  overlays: image tags, replica counts, per-environment configuration.
- `infra-migration/terraform/` — modules for `hetzner` (servers, k3s, load
  balancer), `neon` (managed Postgres), and `cloudflare` (tunnel, DNS), with
  per-environment stacks under `environments/`.

Sequence:

1. **Provision** 💳 — GitHub Actions → Terraform workflow → Run workflow, pick
   the environment and `apply`. This is the manual money gate; review the plan
   output first. Terraform contains no local-exec provisioners.
2. **Bring up the cluster** following
   [`migration/cold-bring-up-runbook.md`](migration/cold-bring-up-runbook.md)
   end to end: registry pull secret, `kustomize edit set image`, External
   Secrets, seed, smoke.
3. **Deploy updates** — Actions → "Deploy to Staging" → Run workflow.
   Manual-only by design.

Secrets flow through External Secrets Operator from a cloud secret manager into
Kubernetes Secrets; `infra-migration/README.md` documents how each value is
generated and populated.

## Operations

**Before routing real traffic**, verify at minimum: the legal pages fit your
jurisdiction, Stripe is in the mode you intend, your email sending domain is
verified, error and uptime monitoring are on, and quota tiers are set
conservatively. These checks need a live deployment, so this document cannot run
them for you.

**Cost control.** The application's own quota tiers are the LLM-spend firewall:
weekly and per-session USD budgets per tier, pre-call quota checks on every
billable surface, server-side settlement of aborted streams, and BYOK so heavy
users can bring their own key. Keep free-tier budgets low until you have real
usage data, and set an explicit $0 on-demand budget with every provider that
holds a card.

**Kill switch.** Path A:
`docker compose -f docker-compose.prod.yml down` stops all compute cost except
the host itself; deleting the host ends everything. Path B: `terraform destroy`
from your workstation (never automated here), or delete the project in the
provider console.

**Never deploy with credentials that were ever committed in plaintext.** Rotate
first. `infra-migration/README.md` covers generation and population.
