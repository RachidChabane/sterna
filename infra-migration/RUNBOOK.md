# Infrastructure Migration Runbook

> **NOTE (2026-05-23 — task 26):** This runbook describes the
> Scaleway-Kapsule-backed staging cluster, which is currently STOPPED
> for cost reasons. The staging plane is migrating to a self-managed
> k3s cluster on Hetzner Cloud. See
> `../docs/migration/cold-bring-up-runbook.md` for the new bring-up
> runbook. This document remains the authority for the
> not-yet-decommissioned Scaleway resources (Secret Manager, R2
> state, Cloudflare zones).

## Overview

This runbook guides you through deploying the Sterna AI platform from local Docker Compose to Kubernetes on Scaleway with Cloudflare and Neon PostgreSQL.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Cloudflare                                │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐             │
│  │   DNS   │  │   WAF   │  │  Tunnel │  │   R2    │             │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘             │
└───────┼────────────┼────────────┼────────────┼──────────────────┘
        │            │            │            │
        └────────────┴─────┬──────┴────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Scaleway Kapsule (Managed K8s)                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                    Node Pool (auto-scaling)                  ││
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    ││
│  │  │API-GW    │  │  Web     │  │ Frontend │  │Orchestr. │    ││
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘    ││
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    ││
│  │  │ Redis    │  │ Sandbox  │  │Egress Prx│  │Consiglier│    ││
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘    ││
│  └─────────────────────────────────────────────────────────────┘│
│  ┌──────────────────────┐                                       │
│  │ Scaleway Container   │                                       │
│  │ Registry             │                                       │
│  └──────────────────────┘                                       │
└─────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Neon PostgreSQL                               │
│  ┌─────────────────┐  ┌─────────────────┐                       │
│  │   Production    │◄─┤    Staging      │ (branch)              │
│  │    Database     │  │    Database     │                       │
│  └─────────────────┘  └─────────────────┘                       │
└─────────────────────────────────────────────────────────────────┘
```

## Prerequisites

- Terraform >= 1.5.0
- kubectl >= 1.29.0
- kustomize >= 5.0.0
- Scaleway account with API credentials
- Cloudflare account with API token
- Neon account with API key

## Phase 1: Account Setup

### 1.1 Scaleway Account

1. Create account at https://console.scaleway.com/
2. Create a new Project for Sterna
3. Generate API credentials:
   - Go to IAM > API Keys
   - Create new API key with full access
   - Note: Access Key, Secret Key, Organization ID, Project ID

### 1.2 Cloudflare Account

1. Log in at https://dash.cloudflare.com/
2. Add your domain (sternaway.ai)
3. Create API token:
   - Go to Profile > API Tokens
   - Create token with Zone:DNS:Edit, Zone:Zone:Read, Cloudflare Tunnel:Edit
4. Note Account ID from the dashboard

### 1.3 Neon Account

1. Create account at https://neon.tech/
2. Create a new project
3. Generate API key from Settings > API

## Phase 2: Infrastructure Provisioning

### 2.1 Configure Terraform Variables

```bash
cd terraform/environments/staging
cp terraform.tfvars.example terraform.tfvars

# Edit terraform.tfvars with your credentials:
# - scaleway_access_key
# - scaleway_secret_key
# - scaleway_project_id
# - scaleway_organization_id
# - cloudflare_api_token
# - cloudflare_account_id
# - neon_api_key
# - domain
```

### 2.2 Initialize and Deploy Staging

```bash
cd terraform/environments/staging

# Initialize Terraform
terraform init

# Plan changes
terraform plan -out=tfplan

# Apply changes
terraform apply tfplan

# Get outputs
terraform output -json > outputs.json
```

### 2.3 Configure kubectl

```bash
# Install Scaleway CLI (if not installed)
brew install scw  # macOS
# or
curl -s https://raw.githubusercontent.com/scaleway/scaleway-cli/master/scripts/get.sh | sh

# Configure Scaleway CLI
scw init

# Get kubeconfig
CLUSTER_ID=$(terraform output -raw cluster_id)
scw k8s kubeconfig get $CLUSTER_ID > ~/.kube/config

# Verify connection
kubectl get nodes
```

## Phase 3: Kubernetes Deployment

### 3.1 Create Secrets

```bash
# Create namespace
kubectl create namespace sterna

# Create secrets (replace with actual values from terraform output)
kubectl create secret generic api-secrets -n sterna \
  --from-literal=JWT_SECRET_KEY='$(terraform output -raw jwt_secret)'

kubectl create secret generic database-secrets -n sterna \
  --from-literal=DATABASE_URL='$(terraform output -raw database_connection_uri)'

kubectl create secret generic llm-secrets -n sterna \
  --from-literal=ANTHROPIC_API_KEY='your-anthropic-key' \
  --from-literal=OPENAI_API_KEY='your-openai-key' \
  --from-literal=OPENROUTER_API_KEY='your-openrouter-key'

kubectl create secret generic storage-secrets -n sterna \
  --from-literal=R2_ACCESS_KEY_ID='$(terraform output -raw r2_access_key_id)' \
  --from-literal=R2_SECRET_ACCESS_KEY='$(terraform output -raw r2_secret_access_key)' \
  --from-literal=R2_BUCKET_NAME='$(terraform output -raw r2_bucket_name)'

kubectl create secret generic cloudflare-tunnel-secret -n sterna \
  --from-literal=TUNNEL_TOKEN='$(terraform output -raw tunnel_token)'

# Create registry pull secret
kubectl create secret docker-registry scaleway-registry -n sterna \
  --docker-server=rg.fr-par.scw.cloud \
  --docker-username=nologin \
  --docker-password='YOUR_SCW_SECRET_KEY'
```

### 3.2 Deploy to Staging

```bash
# Build and apply staging overlay
kustomize build kubernetes/overlays/staging | kubectl apply -f -

# Watch deployment
kubectl rollout status deployment/staging-api-gateway -n sterna
kubectl rollout status deployment/staging-web -n sterna
kubectl rollout status deployment/staging-frontend -n sterna
```

### 3.3 Verify Deployment

```bash
# Check pods
kubectl get pods -n sterna

# Check services
kubectl get svc -n sterna

# Check Cloudflare Tunnel
kubectl logs -n sterna -l app=cloudflare-tunnel

# Test health endpoint
curl https://api-staging.sternaway.ai/health
```

## Phase 4: Database Migration

### 4.1 Export Data from Current Database

```bash
# On current production server (Docker)
docker exec sterna-postgres pg_dump -U postgres sterna_dev > sterna_backup.sql
```

### 4.2 Import to Neon

```bash
# Get Neon connection string from Terraform output
NEON_URL=$(terraform output -raw database_connection_uri)

# Import backup
psql "$NEON_URL" < sterna_backup.sql
```

### 4.3 Run Migrations

```bash
# In web pod
kubectl exec -it deployment/staging-web -n sterna -- python manage.py migrate
```

## Phase 5: Production Deployment

### 5.1 Deploy Production Infrastructure

```bash
cd terraform/environments/production
cp terraform.tfvars.example terraform.tfvars
# Edit with production values

terraform init
terraform plan -out=tfplan
terraform apply tfplan
```

### 5.2 Deploy Production Kubernetes

```bash
# Get production kubeconfig
CLUSTER_ID=$(terraform output -raw cluster_id)
scw k8s kubeconfig get $CLUSTER_ID > ~/.kube/config

# Create secrets (same as staging but with production values)
# ...

# Deploy
kustomize build kubernetes/overlays/production | kubectl apply -f -
```

## Rollback Procedures

### Kubernetes Rollback

```bash
# Rollback specific deployment
kubectl rollout undo deployment/api-gateway -n sterna

# Rollback to specific revision
kubectl rollout undo deployment/api-gateway -n sterna --to-revision=2

# Check rollout history
kubectl rollout history deployment/api-gateway -n sterna
```

### Terraform Rollback

```bash
# Show current state
terraform show

# Restore previous state (if backed up)
terraform state pull > current.tfstate.backup
# ... restore previous state
terraform state push previous.tfstate
```

### Database Rollback

Neon supports instant branching - create a branch before migration, switch back if needed.

## Monitoring & Troubleshooting

### Check Logs

```bash
# All pods in namespace
kubectl logs -n sterna -l app.kubernetes.io/part-of=sterna --tail=100

# Specific service
kubectl logs -n sterna -l app=api-gateway -f

# Previous container (after crash)
kubectl logs -n sterna deployment/web --previous
```

### Check Resource Usage

```bash
kubectl top pods -n sterna
kubectl top nodes
```

### Debug Pod

```bash
kubectl exec -it deployment/web -n sterna -- /bin/sh
```

### Check Events

```bash
kubectl get events -n sterna --sort-by='.lastTimestamp'
```

## Cost Estimates

| Resource | Monthly Cost (Est.) |
|----------|---------------------|
| Scaleway Kapsule (3 nodes PLAY2-NANO) | ~€25 |
| Scaleway Container Registry | Free (up to 75GB) |
| Cloudflare Pro | €20 |
| Neon Pro | €19 |
| **Total** | **~€65** |

*Production with PLAY2-PICO nodes: add ~€20/month*

## GitHub Actions Secrets

Configure these secrets in your repository settings:

| Secret | Description |
|--------|-------------|
| `SCW_ACCESS_KEY` | Scaleway API access key |
| `SCW_SECRET_KEY` | Scaleway API secret key |
| `SCW_ORGANIZATION_ID` | Scaleway organization ID |
| `SCW_PROJECT_ID` | Scaleway project ID |
| `SCW_CLUSTER_ID_STAGING` | Kapsule cluster ID for staging |
| `SCW_CLUSTER_ID_PRODUCTION` | Kapsule cluster ID for production |
| `CLOUDFLARE_API_TOKEN` | Cloudflare API token |
| `NEON_API_KEY` | Neon API key |
| `STAGING_URL` | Staging app URL (https://api-staging.sternaway.ai) |
| `PRODUCTION_URL` | Production app URL (https://api.sternaway.ai) |
| `SLACK_WEBHOOK_URL` | Slack webhook for notifications |

## Emergency Contacts

- Scaleway Support: https://console.scaleway.com/support
- Cloudflare Support: Dashboard > Support
- Neon Support: support@neon.tech

## Maintenance Windows

- Infrastructure updates: Sundays 02:00-06:00 UTC
- Database maintenance: Handled by Neon (auto)
- Kubernetes upgrades: Auto-upgrade enabled (Sunday 3 AM)

---

## Disaster Recovery

### Backup Overview

The platform performs automated daily database backups to Cloudflare R2:

| Schedule | Job | Description |
|----------|-----|-------------|
| 2 AM UTC | `database-backup` | Full PostgreSQL backup to R2 |
| 4 AM UTC | `backup-validation` | Integrity verification of latest backup |

**Retention:** 30 days (managed via R2 lifecycle policy)

### Recovery Time Objectives (RTO/RPO)

| Scenario | RPO | RTO | Method |
|----------|-----|-----|--------|
| Data corruption (< 7 days) | Minutes | 15 min | Neon Point-in-Time Recovery |
| Data corruption (> 7 days) | 24 hours | 30 min | R2 backup restore |
| Complete database loss | 24 hours | 1 hour | R2 + new Neon branch |
| Regional outage | 24 hours | 2 hours | R2 + new Neon project |

### Backup Verification

```bash
# Check CronJob status
kubectl get cronjobs -n sterna -l app.kubernetes.io/component=backup

# View recent backup job history
kubectl get jobs -n sterna -l app.kubernetes.io/component=backup --sort-by=.metadata.creationTimestamp

# Check latest backup job logs
kubectl logs -n sterna -l job-name=staging-database-backup --tail=100

# List backups in R2
# `<cloudflare-account-id>` is the Cloudflare account ID (dashboard URL,
# or `wrangler whoami` / `cloudflare_account_id` in terraform.tfvars).
aws s3 ls s3://sternaway-backups-staging/staging/ \
  --endpoint-url https://<cloudflare-account-id>.r2.cloudflarestorage.com

# Check backup size and timestamp
aws s3 ls s3://sternaway-backups-staging/staging/latest.sql.gz \
  --endpoint-url https://<cloudflare-account-id>.r2.cloudflarestorage.com
```

### Manual Backup Trigger

```bash
# Trigger manual backup
kubectl create job --from=cronjob/staging-database-backup manual-backup-$(date +%Y%m%d%H%M) -n sterna

# Watch backup progress
kubectl logs -n sterna -l job-name=manual-backup-* -f

# Verify in R2
aws s3 ls s3://sternaway-backups-staging/staging/ \
  --endpoint-url https://<cloudflare-account-id>.r2.cloudflarestorage.com
```

### Restore Procedures

#### Option 1: Neon Point-in-Time Recovery (< 7 days, fastest)

Use this for recent data corruption or accidental deletions within the last 7 days.

```bash
# List available restore points (Neon retains 7 days)
neon branches list --project-id <project-id> --org-id org-fragrant-bird-01496838

# Create branch from specific point in time
neon branches create \
  --name "restore-$(date +%Y%m%d)" \
  --parent staging \
  --at "2024-01-15T10:30:00Z" \
  --project-id <project-id> \
  --org-id org-fragrant-bird-01496838

# Get connection string for new branch
neon connection-string \
  --branch "restore-$(date +%Y%m%d)" \
  --project-id <project-id> \
  --org-id org-fragrant-bird-01496838

# Verify data, then promote branch (or update app to use new branch)
# To make this the new main branch:
# 1. Update database-secrets in Scaleway Secret Manager with new connection string
# 2. Restart deployments: kubectl rollout restart deployment -n sterna
```

#### Option 2: R2 Backup Restore to New Branch

Use this when data corruption is older than 7 days.

```bash
# 1. Create a new Neon branch for restoration
neon branches create \
  --name "restore-from-backup-$(date +%Y%m%d)" \
  --parent staging \
  --project-id <project-id> \
  --org-id org-fragrant-bird-01496838

# 2. Get connection string
RESTORE_DB_URL=$(neon connection-string \
  --branch "restore-from-backup-$(date +%Y%m%d)" \
  --project-id <project-id> \
  --org-id org-fragrant-bird-01496838)

# 3. Download backup from R2
aws s3 cp s3://sternaway-backups-staging/staging/latest.sql.gz ./backup.sql.gz \
  --endpoint-url https://<cloudflare-account-id>.r2.cloudflarestorage.com

# Or download a specific backup by date:
aws s3 cp s3://sternaway-backups-staging/staging/backup_20240115_020000.sql.gz ./backup.sql.gz \
  --endpoint-url https://<cloudflare-account-id>.r2.cloudflarestorage.com

# 4. Decompress and restore
gunzip backup.sql.gz
psql "$RESTORE_DB_URL" < backup.sql

# 5. Verify data integrity
psql "$RESTORE_DB_URL" -c "SELECT COUNT(*) FROM auth_user;"
psql "$RESTORE_DB_URL" -c "SELECT COUNT(*) FROM llm_conversation;"

# 6. If restore is successful, update production to use new branch
# Update database-secrets in Scaleway Secret Manager
# Then restart deployments
kubectl rollout restart deployment -n sterna
```

#### Option 3: In-Cluster Restore Job

Use this for automated restoration or when local tools aren't available.

```bash
# Create a restore job (edit the backup filename as needed)
cat <<EOF | kubectl apply -f -
apiVersion: batch/v1
kind: Job
metadata:
  name: database-restore-$(date +%Y%m%d%H%M)
  namespace: sterna
spec:
  backoffLimit: 1
  template:
    spec:
      serviceAccountName: backup
      restartPolicy: Never
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
      containers:
        - name: restore
          image: postgres:16-alpine
          command:
            - /bin/sh
            - -c
            - |
              apk add --no-cache aws-cli

              # Download backup
              aws s3 cp s3://\${R2_BACKUP_BUCKET_NAME}/staging/latest.sql.gz /tmp/backup.sql.gz \
                --endpoint-url "\${R2_ENDPOINT}"

              # Parse DATABASE_URL
              DB_HOST=\$(echo "\$DATABASE_URL" | sed -E 's|.*@([^:]+):([0-9]+)/.*|\1|')
              DB_PORT=\$(echo "\$DATABASE_URL" | sed -E 's|.*@([^:]+):([0-9]+)/.*|\2|')
              DB_NAME=\$(echo "\$DATABASE_URL" | sed -E 's|.*/([^?]+).*|\1|')
              DB_USER=\$(echo "\$DATABASE_URL" | sed -E 's|.*://([^:]+):.*|\1|')
              DB_PASS=\$(echo "\$DATABASE_URL" | sed -E 's|.*://[^:]+:([^@]+)@.*|\1|')
              export PGPASSWORD="\$DB_PASS"

              # Restore
              gunzip -c /tmp/backup.sql.gz | psql -h "\$DB_HOST" -p "\$DB_PORT" -U "\$DB_USER" -d "\$DB_NAME"

              echo "Restore completed"
          envFrom:
            - secretRef:
                name: database-secrets
            - secretRef:
                name: storage-secrets
          resources:
            requests:
              cpu: 200m
              memory: 512Mi
            limits:
              cpu: 1000m
              memory: 2Gi
      volumes:
        - name: tmp
          emptyDir:
            sizeLimit: 5Gi
EOF

# Monitor restore progress
kubectl logs -n sterna -l job-name=database-restore-* -f
```

### Alert Escalation

When backup alerts fire:

1. **Immediate (< 5 min):** Check CronJob logs for error messages
2. **< 15 min:** Verify R2 connectivity and credentials
3. **< 30 min:** Trigger manual backup and debug
4. **< 1 hour:** Escalate to on-call engineer if backup still failing

```bash
# Quick diagnostic
kubectl get events -n sterna --sort-by='.lastTimestamp' | grep -i backup
kubectl describe cronjob staging-database-backup -n sterna
```

### Quarterly DR Testing Checklist

Perform this test quarterly to verify DR procedures work:

- [ ] **Week 1:** Create test Neon branch, restore latest R2 backup
- [ ] **Week 1:** Verify application can connect to restored database
- [ ] **Week 1:** Run smoke tests against restored data
- [ ] **Week 2:** Test Neon PITR by restoring to 24 hours ago
- [ ] **Week 2:** Verify PITR restoration data integrity
- [ ] **Week 3:** Simulate alert by intentionally failing backup
- [ ] **Week 3:** Verify Slack alerts are received
- [ ] **Week 4:** Document any issues, update runbook if needed
- [ ] **Week 4:** Delete test branches and cleanup

```bash
# After testing, cleanup test branches
neon branches delete restore-test-branch --force \
  --project-id <project-id> \
  --org-id org-fragrant-bird-01496838
```

### Secrets Configuration Reference

The following secrets must be configured in Scaleway Secret Manager:

**sternaway-shared-storage-secrets:**
```json
{
  "R2_ACCESS_KEY_ID": "<cloudflare-r2-access-key>",
  "R2_SECRET_ACCESS_KEY": "<cloudflare-r2-secret-key>",
  "R2_BUCKET_NAME": "sternaway-storage",
  "R2_BACKUP_BUCKET_NAME": "sternaway-backups-staging",
  "R2_ENDPOINT": "https://<cloudflare-account-id>.r2.cloudflarestorage.com"
}
```

**sternaway-shared-alerting-secrets:**
```json
{
  "SLACK_WEBHOOK_URL": "https://hooks.slack.com/services/xxx/xxx/xxx"
}
```

To create R2 API token in Cloudflare:
1. Go to R2 > Manage R2 API Tokens
2. Create token with Object Read & Write permissions
3. Scope to `sternaway-backups-*` buckets
