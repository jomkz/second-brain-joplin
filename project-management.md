# Project Management

Astrocyte uses a **GitHub-native, declarative** project-management model. This
document is the one place that describes the whole thing: issue types, labels,
milestones, the Project board, the triage flow, and the declarative sync that
keeps it consistent.

The desired state lives in [`.github/project.yml`](../.github/project.yml) and is
reconciled by [`scripts/project-sync.sh`](../scripts/project-sync.sh). Everything
below explains how to *use* that state.

## Issue types vs. labels

We separate the **kind** of work (issue type) from **where/what** it touches
(labels). Both are set on every triaged issue.

### Issue types (org-level)

The `mkzsystems` org defines five issue types. Pick exactly one per issue:

| Type | Use for |
|------|---------|
| **Epic** | A large, multi-issue initiative tracked via sub-issues |
| **Feature** | A request, idea, or new functionality |
| **Task** | A specific, well-scoped piece of work (incl. docs/chore) |
| **Spike** | A time-boxed investigation that informs follow-on work |
| **Bug** | An unexpected problem or incorrect behavior |

Issue types are set from the **issue-form template** you choose when filing (see
`.github/ISSUE_TEMPLATE/`), or via the sidebar on an existing issue.

### Labels

Labels are grouped by prefix. See [`.github/labels.md`](../.github/labels.md) for
the canonical list.

- **`component:*`** — which part of the codebase (`api`, `cli`, `core`, `agent`,
  `mcp`, `web`, `docker`, `ci`, `docs`, `rag`, `backup`, `network`). On PRs these
  are applied **automatically** by the [labeler](../.github/labeler.yml) based on
  the files changed; on issues they're set during triage.
- **`phase-0..3`** — the roadmap phase a piece of work belongs to (thematic).
- **Meta** — `epic`, `backlog`, `needs-triage`, `blocked`, plus GitHub defaults
  (`good first issue`, `help wanted`, `documentation`, etc.).
- **Dependabot** auto-labels (`dependencies`, `docker`, `github_actions`,
  `python:uv`, `javascript`) are managed by Dependabot and left untouched.

## Milestones

Milestones are **release-versioned** — they answer *when*, while phase labels
answer *what*. They are currently undated.

| Milestone | Roadmap phase | Theme |
|-----------|---------------|-------|
| **v0.2 — Foundation & DX** | phase-0 | Governance, CI, developer experience |
| **v0.3 — Ops Agent & curated apps** | phase-1 | Ops Agent, `aios` CLI, app registry, zero-trust |
| **v0.4 — RAG layer & unified search** | phase-2 | ChromaDB, ingestion, connectors, search |
| **v1.0 — Atomic backup & polish** | phase-3 | Backup/restore, AI-verified recovery, polish |

## The Project board

Work is tracked on the org Project board **[Astrocyte 1.0](https://github.com/orgs/mkzsystems/projects/11)**
(#11). Every open issue is added to the board. Beyond the built-in Status,
Milestone, and Labels fields, the board has these custom fields:

| Field | Type | Notes |
|-------|------|-------|
| **Effort** | single-select | `High` / `Medium` / `Low`; set during planning |
| **Start Date** | date | |
| **Target Date** | date | |
| **Order** | number | manual ordering within a view |

## Triage

Every new issue starts as `needs-triage`. Triaging it means setting:

1. **Issue type** (Epic/Feature/Task/Spike/Bug)
2. **Milestone** (or the `backlog` label if unscheduled)
3. One or more **`component:*`** labels
4. The **phase** label if applicable
5. Its **parent Epic** as a sub-issue, where relevant
6. Add it to the **board** (#11); set **Effort** when it enters active planning

The per-issue checklist also lives in
[CONTRIBUTING.md](../CONTRIBUTING.md#issue-triage-checklist).

## Decision records

Significant **architectural** decisions are captured as ADRs in
[`docs/adr/`](adr/) — that is Astrocyte's decision-record format. The decision to
adopt this PM framework is itself recorded as
[ADR-009](adr/ADR-009-project-management.md).

A heavier, public **RFC** process is deferred to post-1.0 (mirrors the sibling
`uio` project's approach); until then, ADRs cover architectural decisions.

## Declarative sync

`.github/project.yml` is the single source of truth for labels, milestones, the
issue-type taxonomy, and the board's custom fields.
[`scripts/project-sync.sh`](../scripts/project-sync.sh) reconciles it
**non-destructively** (it never deletes entries absent from the spec). It runs:

- **locally** — a maintainer with a `gh` session (`admin:org` + `project`) runs
  `bash scripts/project-sync.sh`; or
- **in CI** — the [`project-sync`](../.github/workflows/project-sync.yml) workflow
  on pushes to `main` that touch the spec, using the `PROJECT_ADMIN_TOKEN`
  secret. Without that secret the script exits cleanly with a warning.

See [`docs/runbooks/github-project-setup.md`](runbooks/github-project-setup.md)
for operator setup (creating the token, first run, board views).

## Deferred / follow-on work

Tracked under the **"Adopt GitHub-native PM framework"** governance Epic:

- ~~Add the `PROJECT_ADMIN_TOKEN` secret so `project-sync` runs unattended.~~ ✅
- ~~Board **auto-add** automation + saved views.~~ ✅
- **DCO sign-off** on commits.
- **REUSE/SPDX** license headers.
- A formal **RFC process** (post-1.0).
