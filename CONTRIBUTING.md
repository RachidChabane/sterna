# Contributing to Sterna

Sterna is a solo-maintained portfolio project, not a project with a
dedicated maintainer team or a formal governance process. That keeps this
document short and practical rather than aspirational: below is what
actually needs to be true for a change to be reviewable, not a process
you're expected to perform theater around.

## Before you start

For anything beyond a small, obvious fix (typo, off-by-one, a clearly
broken test), please open an issue first describing what you want to
change and why. This project has one reviewer with limited bandwidth;
an issue lets us agree on direction before you spend time on a PR that
might not fit.

## Development setup

The full, verified quickstart — prerequisites, environment variables,
`make dev`, service URLs — lives in the root [`README.md`](README.md#quickstart).
Follow that rather than a duplicate copy here; it's the version that's
actually kept in sync with `core/docker-compose.yml`.

In short:

```bash
cd core
cp .env.example .env          # fill in at minimum an OpenRouter API key
make dev                      # docker-compose up -d: web, frontend, gateway, workers, postgres, redis
make migrate
```

Docker services have hot reload for both the Django backend and the Vite
frontend — you don't need to restart a container after editing code, only
after changing dependencies, environment variables, or
`docker-compose.yml` itself.

## Running the tests

Sterna is a monolith (Django + Channels) plus several independent FastAPI
microservices and a separate frontend, so "run the tests" means one of
several commands depending on what you touched. These are the same
commands CI runs in `.github/workflows/ci.yml`; if it passes locally it
should pass there too, modulo environment variables CI injects (see the
workflow for the exact list — mostly dummy JWT secrets and CORS origins).

**Backend (Django), from `core/`, with `requirements.txt` installed in a
venv:**

```bash
pytest -q
```

**Frontend (Vitest + typecheck), from `core/frontend/`:**

```bash
pnpm test           # watch mode
pnpm test -- --run  # single run, as CI runs it
pnpm typecheck
```

**End-to-end (Playwright, the `@smoke` subset CI runs on every push),
from `core/frontend/`:**

```bash
pnpm exec playwright install --with-deps chromium   # once
pnpm exec playwright test --project=chromium --grep @smoke
```

**FastAPI microservices** — each has its own `requirements.txt` and test
suite, run from its own directory:

```bash
cd core/api-gateway && pytest tests/ -v --tb=short
cd core/user-preferences-service && pytest tests/ -v --tb=short
cd core/sandbox/orchestrator && pytest -c /dev/null tests/ -v --tb=short
```

(The `-c /dev/null` on the orchestrator suite is not optional: that
directory has no pytest config of its own, so pytest would otherwise walk
up to `core/pytest.ini` and pick up Django-only options that don't apply
here.)

**Infrastructure runbook lint**, from the repo root:

```bash
pytest infra-migration/tests/test_runbook.py -q
```

Only run the suites relevant to what you changed — you don't need a
Kubernetes cluster or Scaleway credentials to touch frontend code, and you
don't need Node/pnpm to touch the Django backend.

## Commit messages: Conventional Commits

Commit subjects on `master` and `develop` are parsed by CI
(`.github/workflows/ci.yml`) to decide how to bump each affected
service's version in `core/versions.json`, so the prefix isn't just
style — it drives the release:

| Prefix | Effect |
|---|---|
| `fix: ...` | patch bump (1.0.0 → 1.0.1) |
| `feat: ...` | minor bump (1.0.0 → 1.1.0) |
| `feat!: ...` or a `BREAKING CHANGE:` footer | major bump (1.0.0 → 2.0.0) |
| anything else (`chore:`, `docs:`, `refactor:`, `test:`, ...) | patch bump, or no version-affecting behavior if the commit touches no service directory |

The bump only applies to services whose paths actually changed (see the
`paths-filter` block in `ci.yml` for the exact directory → service
mapping), so a `docs/` or `frontend/`-only change won't bump the backend's
version and vice versa. Use a real prefix even for small changes —
`fix:`/`feat:` on an unrelated commit will bump versions incorrectly.

## Pull requests

- Keep PRs scoped to one change. A PR that mixes a bug fix with an
  unrelated refactor is harder to review and harder to revert if
  something breaks.
- Include the tests you ran (or added) for the change — see the commands
  above. New behavior should come with a new test where the existing
  suites don't already cover it; this repo tries to keep unit, adapter,
  and end-to-end coverage as described in the project's own code-quality
  conventions, not just a passing CI badge.
- CI must be green (lint, backend, frontend, microservice, and Playwright
  smoke jobs) before a PR is merged. There's no separate "manual QA"
  step — the suites above are the gate.
- Response times are best-effort: this is a single maintainer's portfolio
  project, not a funded team. If a PR sits without a response, a polite
  ping after a week or two is fine.
- By submitting a contribution, you agree it's licensed under this
  project's [Apache License, Version 2.0](LICENSE) (inbound = outbound),
  consistent with the license grant in that file.

## Reporting bugs

Open a GitHub issue with steps to reproduce, what you expected, and what
actually happened. For anything that looks like a security
vulnerability, do not open a public issue — see [`SECURITY.md`](SECURITY.md)
instead.

## Code of conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md). Be
respectful; report problems as described there.
