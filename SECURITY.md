# Security Policy

## Supported versions

Sterna is a single-maintainer project with one deployed line of
development: `master`. There are no maintained release branches or
long-term-support versions — only the latest commit on `master` receives
security fixes.

| Version | Supported |
|---|---|
| `master` (latest) | ✅ |
| Anything older / a fork | ❌ |

If you're running an older checkout, update to the latest `master` before
reporting an issue — it may already be fixed.

## Reporting a vulnerability

**Please do not open a public GitHub issue for a security vulnerability.**
Public issues are searchable and get indexed immediately; that turns a
report into a how-to before a fix ships.

Instead, report privately through **GitHub Security Advisories** on this
repository:

1. Go to the repository's **Security** tab.
2. Click **Report a vulnerability** (under "Advisories").
3. Describe the issue: what it is, where it lives (file/endpoint/service),
   how to reproduce it, and its potential impact.

This opens a private advisory visible only to the maintainer and you,
with a dedicated space to discuss the issue and coordinate a fix before
anything is disclosed publicly.

If GitHub Security Advisories is ever unavailable to you, open a regular
issue asking to be contacted for a private report — without including any
vulnerability details in the issue itself.

## What to expect

This is a solo-maintained portfolio project, not a company with a
dedicated security team or an SLA. As a realistic target rather than a
guarantee:

- **Acknowledgement**: within a few days of the report.
- **Triage / next steps**: within roughly two weeks, depending on
  severity and the maintainer's availability.
- **Fix and disclosure**: coordinated with you — the advisory stays
  private until a fix is available, then is published (crediting you,
  unless you'd rather stay anonymous).

There is no bug bounty program.

## Scope

In scope: the application code in this repository — the Django/DRF
backend, the FastAPI microservices, the React frontend, the sandbox
orchestrator and its container isolation, and the Kubernetes/Terraform
manifests under `infra-migration/`.

Out of scope: vulnerabilities in third-party dependencies themselves
(report those upstream — see [`NOTICE`](NOTICE) for the third-party
components this project bundles), and anything requiring physical or
social-engineering access rather than a flaw in the software.

## Further reading

For background on how a specific security-sensitive area of the codebase
is designed (not a substitute for reporting a vulnerability through the
process above):

- [`core/mcp/docs/security-design.md`](core/mcp/docs/security-design.md) —
  how OAuth tokens for MCP connectors are encrypted and handled at rest.
