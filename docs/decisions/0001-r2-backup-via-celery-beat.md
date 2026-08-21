# 0001 — R2 backup runs as a Celery beat task, not a Cloudflare Worker

- Status: Accepted.
- Date: 2026-05-21.

## Context

Task 22 offered two options for the daily R2 backup runner:

a. a new Cloudflare Worker;
b. a Celery beat task on the orchestrator.

## Decision

Celery beat.

## Rationale

1. The Celery beat deployment already exists in
   `infra-migration/kubernetes/base/celery-beat/`. Adding a
   beat-schedule entry is a single-file change.
2. A Cloudflare Worker would need its own deploy pipeline, wrangler
   config, secret rotation, observability, and a third way to access
   R2 credentials. None of that yields functional benefit; the backup
   task is daily and CPU-trivial.
3. Sentry integration for failure alerting is already wired into the
   Django/Celery process. A Worker would need an independent Sentry
   SDK and DSN.
4. Re-running the backup on demand from `manage.py shell` or via
   `kubectl exec` is straightforward against Celery. A Worker would
   require a custom HTTP trigger.

## Trade-off accepted

A worker outage suspends backups until the worker recovers. The
stale-backup alert catches a suspended scheduler within 30 hours.
