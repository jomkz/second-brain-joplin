# Project Management

`second-brain-joplin` uses a **GitHub-native** project-management model: issue
types describe the *kind* of work, labels describe *where/what* it touches, and
milestones describe *when* it ships. This document explains how to use them.

The declarative label/milestone spec lives in
[`.github/project.yml`](../.github/project.yml). It is applied manually via the
`gh` CLI or the GitHub UI — there is no automated sync at this stage.

## Issue types vs. labels

We separate the **kind** of work (issue type) from **where/what** it touches
(labels). Both are set on every triaged issue.

### Issue types

Issue types are set from the **issue-form template** chosen when filing (see
[`.github/ISSUE_TEMPLATE/`](../.github/ISSUE_TEMPLATE/)), or via the sidebar on
an existing issue. Pick exactly one:

| Type | Use for |
|------|---------|
| **Epic** | A large, multi-issue initiative tracked via sub-issues |
| **Feature** | A request, idea, or new functionality |
| **Task** | A specific, well-scoped piece of work (incl. docs/chore) |
| **Spike** | A time-boxed investigation that informs follow-on work |
| **Bug** | An unexpected problem or incorrect behavior |

### Labels

Labels are grouped by prefix; the canonical list is in
[`.github/project.yml`](../.github/project.yml).

- **`component:*`** — which part of the codebase: `joplin-api`, `mcp`, `search`,
  `docs`, `ci`, `templates`. On PRs these are applied **automatically** by the
  [labeler](../.github/labeler.yml) based on the files changed; on issues they
  are set during triage.
- **`phase-0..3`** — the roadmap phase a piece of work belongs to (thematic):
  bootstrap, core read tools, semantic search, write workflow & publish.
- **Meta** — `epic`, `backlog`, `needs-triage`, `blocked`, plus GitHub defaults
  (`good first issue`, `help wanted`).
- **Dependabot** auto-labels (`dependencies`, `github_actions`) are managed by
  [Dependabot](../.github/dependabot.yml) and left untouched.

## Milestones

Milestones are **release-versioned** — they answer *when*, while phase labels
answer *what*. They are currently undated.

| Milestone | Roadmap phase | Theme |
|-----------|---------------|-------|
| **v0.1 — Bootstrap** | phase-0 | Repo scaffold, CI, package skeleton |
| **v0.2 — Core Read Tools** | phase-1 | All read MCP tools working against Joplin |
| **v0.3 — Semantic Search** | phase-2 | Embedding index and semantic search |
| **v0.4 — Write Workflow** | phase-3 | Human-gated note creation |
| **v1.0 — Publish** | phase-3 | PyPI release, full docs, Joplin templates |

## Triage

Every new issue starts as `needs-triage`. Triaging it means setting:

1. **Issue type** (Epic / Feature / Task / Spike / Bug)
2. **Milestone** (or the `backlog` label if unscheduled)
3. One or more **`component:*`** labels
4. The **phase** label if applicable
5. Its **parent Epic** as a sub-issue, where relevant

The same checklist lives in
[CONTRIBUTING.md](../CONTRIBUTING.md#issue-triage-checklist).

## Possible future work

Not in place today; noted so the model can grow without surprises:

- An org-level Project board with custom fields (Effort, target dates).
- A declarative sync script/workflow to reconcile `.github/project.yml`
  automatically instead of applying it by hand.
- Architectural decision records (ADRs) and a heavier RFC process.
