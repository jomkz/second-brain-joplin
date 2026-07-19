# Project Management

`second-brain-joplin` uses a **GitHub-native** project-management model: the *kind*
of work is carried by the issue-form templates (and the `epic` label for epics),
labels describe *where/what* it touches, and milestones describe *when* it ships.
This document explains how to use them. It follows the **personal edition** of the
[pm-framework](https://github.com/mkzsystems/pm-framework); this is a personal
GitHub account, so org-level native issue types are not available.

The declarative label/milestone spec lives in
[`.github/project.yml`](../.github/project.yml). It is applied manually via the
`gh` CLI or the GitHub UI — there is no automated sync at this stage.

## Kind of work vs. labels

We separate the **kind** of work from **where/what** it touches (labels). Both are
set on every triaged issue.

### Kind of work

Personal accounts do not have GitHub's org-level issue types, so the kind of work
is carried by the **issue-form template** chosen when filing (see
[`.github/ISSUE_TEMPLATE/`](../.github/ISSUE_TEMPLATE/)), and **epics are marked
with the `epic` label** (+ native sub-issues). Pick exactly one kind:

| Kind | Use for |
|------|---------|
| **Epic** | A large, multi-issue initiative tracked via sub-issues (`epic` label) |
| **Feature** | A request, idea, or new functionality |
| **Task** | A specific, well-scoped piece of work (incl. docs/chore) |
| **Spike** | A time-boxed investigation that informs follow-on work |
| **Bug** | An unexpected problem or incorrect behavior |

### Labels

Labels are grouped by prefix; the canonical list is in
[`.github/project.yml`](../.github/project.yml).

- **`component:*`** — which part of the codebase: `joplin-api`, `mcp`, `search`,
  `docs`, `ci`, `templates`. On PRs these are applied **automatically** by the
  [labeler workflow](../.github/workflows/labeler.yml) (runs on PR
  open/sync/reopen) from the path rules in
  [`.github/labeler.yml`](../.github/labeler.yml); on issues they are set during
  triage.
- **Meta** — `epic`, `backlog`, `needs-triage`, `blocked`, plus GitHub defaults
  (`good first issue`, `help wanted`).
- **Dependabot** auto-labels (`dependencies`, `github_actions`) are managed by
  [Dependabot](../.github/dependabot.yml) and left untouched.

## Milestones

Milestones are the phases — one milestone per roadmap phase, named by theme. They
answer *when* a piece of work ships; there are deliberately no `phase-*` labels
(the milestone is the phase). They are currently undated.

| Milestone | Theme |
|-----------|-------|
| **v0.1 — Bootstrap** | Repo scaffold, CI, package skeleton |
| **v0.2 — Core Read Tools** | All read MCP tools working against Joplin |
| **v0.3 — Semantic Search** | Embedding index and semantic search |
| **v0.4 — Write Workflow** | Human-gated note creation |
| **v1.0 — Publish** | PyPI release, full docs, Joplin templates |

## Triage

Every new issue starts as `needs-triage`. Triaging it means setting:

1. **Kind** (Epic via the `epic` label / Feature / Task / Spike / Bug via template)
2. **Milestone** (or the `backlog` label if unscheduled)
3. One or more **`component:*`** labels
4. Its **parent Epic** as a sub-issue, where relevant

The same checklist lives in
[CONTRIBUTING.md](../CONTRIBUTING.md#issue-triage-checklist).

## CI and branch protection

Quality gates live in a single reusable workflow,
[`.github/workflows/checks.yml`](../.github/workflows/checks.yml), invoked by both
[`ci.yml`](../.github/workflows/ci.yml) (push/PR to `main`) and
[`release.yml`](../.github/workflows/release.yml) (before publishing). See
[CONTRIBUTING.md](../CONTRIBUTING.md#how-ci-works).

To require CI green before merge, an operator enables branch protection on `main`
(Settings → Branches) and marks these status checks as **required**:

- `checks / Lint`
- `checks / Type check`
- `checks / Build and validate package`
- `checks / Test (Python 3.11)`
- `checks / Test (Python 3.12)`
- `checks / Test (Python 3.13)`

(Check names are `<caller job> / <job name>`; they appear in the checks list on
the first PR once the workflow has run.)

A separate [`labeler.yml`](../.github/workflows/labeler.yml) workflow runs on
`pull_request_target` to apply `component:*` labels (see [Labels](#labels)
above). It is **advisory** — deliberately *not* a required status check, so it
never gates a merge.

## Possible future work

Not in place today; noted so the model can grow without surprises:

- An org-level Project board with custom fields (Effort, target dates).
- A declarative sync script/workflow to reconcile `.github/project.yml`
  automatically instead of applying it by hand.
- Architectural decision records (ADRs) and a heavier RFC process.
