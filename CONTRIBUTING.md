# Contributing

Thanks for your interest in second-brain-joplin.

## Development setup

```bash
git clone https://github.com/jomkz/second-brain-joplin
cd second-brain-joplin
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Or with `uv`:

```bash
uv sync
```

## Running tests

```bash
pytest
```

## Running the server locally

```bash
cp .env.example .env
# Edit .env with your Joplin API token
python -m second_brain_joplin.server
```

## Issue triage checklist

Every triaged issue should have:

1. **Issue type** — Epic / Feature / Task / Spike / Bug (set via sidebar)
2. **Milestone** — which release it targets (or `backlog` label if unscheduled)
3. One or more **`component:*`** labels
4. **Phase label** if applicable (`phase-0` through `phase-3`)
5. **Parent Epic** set as a sub-issue where relevant

## Label conventions

| Prefix | Values | Applied by |
|---|---|---|
| `component:` | `joplin-api`, `mcp`, `search`, `docs`, `ci`, `templates` | Maintainer (issues); labeler bot (PRs) |
| `phase-` | `phase-0`, `phase-1`, `phase-2`, `phase-3` | Maintainer |
| meta | `epic`, `backlog`, `needs-triage`, `blocked`, `good first issue`, `help wanted` | Maintainer |

## Commit style

No strict convention yet — use a short imperative summary line. DCO sign-off (`git commit -s`) is encouraged but not enforced at this stage.

## Pull requests

- Target `main`.
- Keep PRs focused — one logical change per PR.
- Add or update tests for any new behavior.
- CI must pass before merge.
