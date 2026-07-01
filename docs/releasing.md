# Releasing

Releases are published to **PyPI** by the
[`release`](../.github/workflows/release.yml) workflow using an OIDC
**trusted publisher** — no API tokens are stored in the repo.

On a `v*` tag push the workflow first runs the full **checks** suite (lint,
type-check, the test matrix, and package build) on the tagged commit via the
shared [`checks`](../.github/workflows/checks.yml) reusable workflow. A red check
**blocks the publish**. The artifact that is published is the exact sdist + wheel
built and tested in that suite — the publish job does not rebuild. Re-publishing
a version that already exists on PyPI is skipped (`skip-existing`), so re-running
a release is safe.

## One-time operator setup

1. **Trusted publisher on PyPI** (already configured for this repo): a GitHub
   publisher on <https://pypi.org> with owner `jomkz`, repository
   `second-brain-joplin`, workflow `release.yml`, environment `pypi`.
   To re-check or recreate it: **Manage project → Publishing** (or
   **Account → Publishing → Add a pending publisher** before the project's first
   release).
2. **GitHub environment:** create an Actions environment named **`pypi`**
   (Settings → Environments → New environment). The workflow declares
   `environment: pypi`, and the name must match the trusted-publisher config
   exactly. Optionally add a required reviewer to gate publishes.

## Cutting a release

1. Bump the version in
   [`src/second_brain_joplin/__init__.py`](../src/second_brain_joplin/__init__.py)
   — this is the single source of truth (hatch reads it dynamically). Update
   [`CHANGELOG.md`](../CHANGELOG.md).
2. Commit, then tag with a matching `v<version>` tag and push it:

   ```bash
   git tag v0.1.0
   git push origin v0.1.0
   ```

   The tag push triggers the workflow. You can also run it manually from the
   Actions tab (**Run workflow** / `workflow_dispatch`).
3. The workflow runs the full `checks` suite (lint, type-check, tests, and
   `uv build` + `twine check`), then — only if everything is green — publishes
   the tested sdist + wheel to PyPI.

## Verify

Install from PyPI and confirm the server starts:

```bash
uvx second-brain-joplin serve
```
