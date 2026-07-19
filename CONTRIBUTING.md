# Contributing

Thanks for your interest in second-brain-joplin.

## Development setup

We use [uv](https://docs.astral.sh/uv/) as the primary toolchain:

```bash
git clone https://github.com/jomkz/second-brain-joplin
cd second-brain-joplin
uv sync
uv run pre-commit install   # enable lint/format on commit
```

<details>
<summary>pip fallback</summary>

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[test]"
```
</details>

## Running tests

```bash
uv run pytest
```

Coverage is printed on every run. The **90% coverage gate is enforced in CI**
(not in `addopts`, so running a subset of tests locally won't spuriously fail).
Reproduce the gate locally with:

```bash
uv run pytest --cov-fail-under=90
```

### Semantic search & optional extras

The semantic-search stack (embedding model + vector store) lives behind optional
extras (`[semantic]`, `[semantic-chroma]`, `[semantic-st]`), so a plain `uv sync`
and the test suite need **none** of them — the tests drive the orchestration in
`src/second_brain_joplin/semantic/` through in-memory fakes (`tests/fakes.py`).
The concrete backends in `semantic/backends.py` are the only code that imports
the heavy libs (lazily), so they're omitted from coverage and validated
separately. To exercise semantic search for real, install a backend combo and
run `joplin_reindex`:

```bash
uv sync --extra semantic                 # sqlite-vec + FastEmbed (light default)
# or: uv sync --extra semantic --extra semantic-st      # bge-m3 via sentence-transformers
# or: uv sync --extra semantic --extra semantic-chroma  # ChromaDB vector store
```

## Linting and type checking

```bash
uvx pre-commit run --all-files   # ruff lint + format + actionlint (the authoritative gate)
uv run mypy                      # strict static type checking (src + tests)
```

`.pre-commit-config.yaml` is the single source of truth for lint tooling and
versions — CI runs the exact same `pre-commit run --all-files`. It also runs
`actionlint` over `.github/workflows/*.yml`, so workflow-syntax regressions are
caught locally. mypy runs in `strict` mode over both `src` and `tests`
(configured in `pyproject.toml`).

## How CI works

All quality gates live in one reusable workflow,
[`.github/workflows/checks.yml`](.github/workflows/checks.yml) — **lint**,
**typecheck**, a **test** matrix (Python 3.11/3.12/3.13), and a **build** job
that builds the package, runs `twine check`, and smoke-tests the wheel. Both
[`ci.yml`](.github/workflows/ci.yml) (on push/PR to `main`) and
[`release.yml`](.github/workflows/release.yml) (before publishing to PyPI) call
it, so nothing merges or ships without passing the same checks. Run `uv sync
--locked` locally to match CI's locked environment.

A separate [`labeler.yml`](.github/workflows/labeler.yml) workflow applies
`component:*` labels to PRs from the file paths changed — advisory only, not a
merge gate.

## Running the server locally

```bash
cp .env.example .env
# Edit .env with your Joplin API token; it is loaded automatically via python-dotenv
uv run second-brain-joplin serve
```

## Issue triage checklist

See [docs/project-management.md](docs/project-management.md) for the full model
(kind of work, labels, milestones). Every triaged issue should have:

1. **Kind** — Epic (via the `epic` label) / Feature / Task / Spike / Bug (via the
   issue-form template; personal accounts have no org-level issue types)
2. **Milestone** — which release it targets (or `backlog` label if unscheduled)
3. One or more **`component:*`** labels
4. **Parent Epic** set as a sub-issue where relevant

## Label conventions

| Prefix | Values | Applied by |
|---|---|---|
| `component:` | `joplin-api`, `mcp`, `search`, `docs`, `ci`, `templates` | Maintainer (issues); [labeler bot](.github/workflows/labeler.yml) (PRs) |
| meta | `epic`, `backlog`, `needs-triage`, `blocked`, `good first issue`, `help wanted` | Maintainer |

## Commit style

No strict convention yet — use a short imperative summary line. DCO sign-off (`git commit -s`) is encouraged but not enforced at this stage.

## Pull requests

- Target `main`.
- Keep PRs focused — one logical change per PR.
- Add or update tests for any new behavior.
- CI must pass before merge.
