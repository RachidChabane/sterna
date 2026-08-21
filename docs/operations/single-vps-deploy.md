# Single-VPS production deploy (docker compose)

**Status**: authored 2026-07 — artifacts verified offline (`docker
compose config`), no live deployment performed yet.
**Artifacts**: `core/docker-compose.prod.yml`,
`core/.env.production.example` (this doc walks through both).
**Audience**: an operator with a credit card and a domain on
Cloudflare. Everything else is copy-paste.

This is the cheapest credible production path: one Hetzner VPS
(~16–17 EUR/mo), docker compose, and a Cloudflare tunnel as the only
ingress. It trades away HA, autoscaling and pod isolation — the k8s
path (`docs/migration/`) is the grown-up option; this one is for
small/early production and staging-on-a-budget.

> **HARD WARNING — no auto-created cloud resources.**
> Nothing in this runbook (or in the compose file) creates, resizes or
> bills any cloud resource by itself. Every step that costs money is an
> explicit manual action called out with its price. If a command in
> this doc surprises you with a bill, that is a bug in this doc — file
> an issue.

Priced steps in this runbook:

| # | Step | Cost (June 2026 — verify before buying) |
|---|---|---|
| 1 | Hetzner CX43 VPS | ~16.4 EUR/mo (8 vCPU / 16 GB / 160 GB NVMe) |
| 6 | Cloudflare tunnel | free plan is sufficient |
| 9 | R2 backup bucket | ~0 at this scale (10 GB free, then ~0.015 USD/GB/mo) |
| — | Neon PostgreSQL (optional swap-in) | free tier or from ~5 USD/mo |

---

## 1. Provision the VPS (manual, priced)

In the Hetzner Cloud console (https://console.hetzner.cloud):

1. Create a project → Add Server.
2. Location: `fsn1`/`nbg1` (EU). Image: **Ubuntu 24.04**.
3. Type: **CX43** — 8 vCPU / 16 GB RAM / 160 GB NVMe,
   **~16.4 EUR/mo incl. VAT as of June 2026** (check the console; the
   memory limits in `docker-compose.prod.yml` are budgeted for 16 GB).
   A CX33 (8 GB) does NOT fit this stack.
4. Add your SSH key. Enable the free Hetzner firewall: allow inbound
   **22/tcp from your IP only** — nothing else. The app needs NO open
   inbound ports (the Cloudflare tunnel dials out).
5. Create. Note the IPv4.

No Terraform here on purpose: one pet server, dashboard-managed.
If this box multiplies, graduate to `infra-migration/`.

## 2. Install Docker + compose plugin

SSH in as root:

```bash
apt-get update && apt-get install -y ca-certificates curl git
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  -o /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update && apt-get install -y docker-ce docker-ce-cli \
  containerd.io docker-buildx-plugin docker-compose-plugin
docker compose version   # v2.24+ required (env_file/profiles syntax)
```

## 3. Clone the repo

```bash
git clone git@github.com:<owner>/<repo>.git /opt/sterna
cd /opt/sterna/core
```

(Private repo: use a fine-grained deploy key or a read-only PAT.)

## 4. Create `.env.production`

```bash
cp .env.production.example .env.production
chmod 600 .env.production
vim .env.production
```

Uncomment and fill. The template marks which vars are **[REQUIRED]**
— `sterna/settings/prod.py` fail-louds on Resend, Turnstile and
Stripe keys, so the web container will crash-loop until they are set
(empty string is acceptable only for `STRIPE_WEBHOOK_SECRET`).
Generation instructions per secret: `infra-migration/README.md`.

Database choice, decide now:

- **Local postgres (default)**: set `POSTGRES_PASSWORD`, leave
  `DATABASE_URL` unset. Data lives in the `postgres_data_prod` volume
  on the VPS — you own backups (step 9).
- **Neon (managed)**: set `DATABASE_URL` to the Neon DSN. The local
  postgres service still starts but nothing uses it; you may remove it
  from the compose file. Backups/PITR are then Neon's job and step 9
  shrinks to media files.

## 5. Build or pull images

**Option A — pull from GHCR** (built by `.github/workflows/ci.yml`):

```bash
# Read-only PAT with read:packages — see infra-migration/README.md
docker login ghcr.io -u <github-user>
# In .env.production: GHCR_OWNER=<lowercased owner>, IMAGE_TAG=master-latest
# (or a pinned semver / commit SHA — same tag scheme as ci.yml)
docker compose --env-file .env.production -f docker-compose.prod.yml pull
```

**Option B — build on the VPS** (no registry account needed, ~10 min):

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml build
```

Frontend caveat (either option): `VITE_*` values are baked into the
static bundle at **build** time, not read at runtime. The shipped
nginx config serves the app and proxies `/api`, `/admin`, `/static`,
`/media` to `web:8000` same-origin, so the defaults work when users
browse `app.<domain>`. If the bundle must call `api.<domain>`
directly instead, write `core/frontend/.env.production` (VITE_API_URL
etc.) before building — which forces Option B.

## 6. Create the Cloudflare tunnel (manual, dashboard)

Cloudflare dashboard → Zero Trust → Networks → Tunnels →
**Create a tunnel** (Cloudflared connector):

1. Name it (e.g. `sterna-vps`). Copy the **token** shown in the
   install command → put it in `.env.production` as
   `CLOUDFLARE_TUNNEL_TOKEN`. Do NOT run their install command — the
   `cloudflared` compose service is the connector.
2. Add **public hostnames** in this exact order (first match wins):

   | Order | Hostname | Path | Service |
   |---|---|---|---|
   | 1 | `api.<domain>` | `ws/*` | `http://web:8000` |
   | 2 | `api.<domain>` | (empty) | `http://api-gateway:8080` |
   | 3 | `app.<domain>` | (empty) | `http://frontend:80` |

   Why row 1: Django Channels WebSockets (`/ws/voice-rooms/…`,
   `/ws/code-sessions/…`) are served by the ASGI web container; the
   api-gateway only proxies REST routes plus its own
   `/api/v1/sandbox/ws/*` — generic `/ws` paths would 404 there.
   Service hostnames resolve on the compose network because
   cloudflared runs inside it; that is also why **no container maps a
   host port**.
3. DNS records for both hostnames are created automatically when you
   save the public hostnames (proxied CNAMEs to the tunnel).

## 7. First start, migrate, seed, first user

```bash
cd /opt/sterna/core
docker compose --env-file .env.production -f docker-compose.prod.yml up -d
watch docker compose --env-file .env.production -f docker-compose.prod.yml ps
# wait until web/postgres/redis are "healthy"

# Migrations (the k8s path runs these in an initContainer; here it's manual)
docker compose --env-file .env.production -f docker-compose.prod.yml \
  exec web python manage.py migrate --noinput

# Seed reference data (idempotent; includes Stripe price sync)
docker compose --env-file .env.production -f docker-compose.prod.yml \
  exec web python manage.py seed_all

# First admin user
docker compose --env-file .env.production -f docker-compose.prod.yml \
  exec web python manage.py createsuperuser
```

The tunnel comes up in seconds — dashboard shows the connector as
HEALTHY, and `docker compose … logs cloudflared` shows
`Registered tunnel connection`.

## 8. Smoke verification

In-container (service-to-service, before/after DNS):

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml \
  exec web bash -c 'SMOKE_BASE_URL=http://web:8000 python -m pytest smoke/ -v --tb=short'
```

Public URL (from your workstation — final gate):

```bash
cd core
pip install pytest==8.3.4 httpx==0.28.1
SMOKE_BASE_URL=https://api.<domain> \
SMOKE_TEST_USER_PASSWORD="<from .env.production>" \
pytest -c /dev/null smoke/ -v --tb=short
```

(`-c /dev/null` bypasses `core/pytest.ini`, same trick as the
cold-bring-up runbook step 14. Tests skip cleanly when optional
`SMOKE_*` vars are unset.) Then browse `https://app.<domain>` and log
in as the superuser.

## 9. Backups (single VPS = you are the backup team)

Skip this section if you chose Neon (it has PITR); media files are
already in R2 when the `R2_*` vars are set.

For local postgres, a plain host cron + `pg_dump` + rclone to R2 —
deliberately the same shape as the k8s backup CronJob
(`infra-migration/kubernetes/base/backup/configmap.yaml`), minus the
cluster:

```bash
apt-get install -y rclone
rclone config   # remote "r2": type=s3, provider=Cloudflare,
                # access_key_id/secret from the R2 API token (storage-secrets),
                # endpoint=https://<account-id>.r2.cloudflarestorage.com

cat > /usr/local/bin/sterna-backup.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
cd /opt/sterna/core
STAMP=$(date -u +%Y%m%d-%H%M%S)
docker compose --env-file .env.production -f docker-compose.prod.yml \
  exec -T postgres pg_dump -U postgres -d sterna -Fc \
  > /var/backups/sterna-${STAMP}.dump
rclone copy /var/backups/sterna-${STAMP}.dump r2:sterna-backups-vps/postgres/
find /var/backups -name 'sterna-*.dump' -mtime +7 -delete
EOF
chmod +x /usr/local/bin/sterna-backup.sh
mkdir -p /var/backups
( crontab -l 2>/dev/null; echo "0 2 * * * /usr/local/bin/sterna-backup.sh" ) | crontab -
```

Create the `sterna-backups-vps` R2 bucket manually in the
Cloudflare dashboard first (priced step — free tier covers this
scale). To restore, `rclone copy` the dump back down and run
`pg_restore` against the target database. **Test a restore once
before you need it.**

## 10. Upgrades

```bash
cd /opt/sterna
git pull

cd core
# Option A (GHCR): bump IMAGE_TAG in .env.production, then
docker compose --env-file .env.production -f docker-compose.prod.yml pull
# Option B (local build):
docker compose --env-file .env.production -f docker-compose.prod.yml build

# Take a backup first (step 9 script), then:
docker compose --env-file .env.production -f docker-compose.prod.yml up -d
docker compose --env-file .env.production -f docker-compose.prod.yml \
  exec web python manage.py migrate --noinput

docker image prune -f   # reclaim disk from superseded images
```

`up -d` only recreates containers whose image/config changed.
Rollback = check out the previous tag / set the previous `IMAGE_TAG`
and repeat (reverse migrations are NOT automatic — restore the step-9
dump if a migration must be undone).

## Appendix A — optional sandbox profile (coding agent)

The orchestrator + egress-proxy services are behind
`--profile sandbox` and OFF by default:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml \
  --profile sandbox up -d
```

**Security tradeoff, in plain words**: the orchestrator mounts
`/var/run/docker.sock` and runs as root — that is root on the VPS. A
break-out from a coding-agent sandbox it spawns compromises the entire
box, including `.env.production` and the database. The k8s path
isolates this with gVisor + NetworkPolicies; a single VPS cannot.
Leave it off unless the coding-agent feature is genuinely needed, and
assume the whole host is the blast radius.

## Appendix B — memory budget (16 GB)

Limits from `docker-compose.prod.yml`: web 4G, celery-worker 3G,
postgres 2G, redis 768M, celery-beat/api-gateway/user-preferences/
google-maps 512M each, brave-search 384M, frontend/cloudflared 256M
each ≈ **12.9 GB**; sandbox profile adds orchestrator 1G +
egress-proxy 256M ≈ **14.2 GB**, leaving ~1.8 GB for the OS, page
cache and spawned sandbox containers (themselves capped at
`SANDBOX_MEMORY_LIMIT=2g` — mind the ceiling when the profile is on).
