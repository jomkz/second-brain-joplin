# Releasing

Releases are published to **PyPI** by the
[`release`](../.github/workflows/release.yml) workflow using an OIDC
**trusted publisher** — no API tokens are stored in the repo.

On a `v*` tag push the workflow first runs the full **checks** suite (lint,
type-check, the test matrix, the package build, and the smoke test of the built
wheel on Linux, macOS and Windows) on the tagged commit via the
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
2. Commit and merge that to `main`, then put a signed, matching `v<version>` tag
   on the merged commit and push it:

   ```bash
   git tag -s v1.0.0 -m "v1.0.0 — Publish"
   git push origin v1.0.0
   ```

   The tag push triggers the workflow. You can also run it manually from the
   Actions tab (**Run workflow** / `workflow_dispatch`).
3. The workflow runs the full `checks` suite (lint, type-check, tests,
   `uv build` + `twine check`, and the smoke test), then — only if everything is
   green — publishes the tested sdist + wheel to PyPI.
4. Once PyPI has it, the workflow creates the **GitHub Release** for the tag with
   [`scripts/github-release.sh`](../scripts/github-release.sh): the title and
   notes come from the version's `## [<version>]` section of `CHANGELOG.md`
   (the run fails if that section is missing or empty), the sdist + wheel are
   attached, and a pre-release version (`0.4.0rc1`, `0.4.0b2`, `0.4.0-rc.1`) is
   marked as a pre-release. Re-running updates the existing release instead of
   failing.

To create or refresh the release for an older tag by hand (for example
`v0.2.0`, which predates this step), run the script from a checkout of `main`
with `gh` logged in: `scripts/github-release.sh v0.2.0`.

## Verify

Start the published version the way a user does and talk MCP to it. This is
the check the workflow ran against the wheel, now against PyPI:

```bash
uv run scripts/smoke.py --from "second-brain-joplin==1.0.0" --expect 1.0.0
```

PyPI can take a minute to offer a new version. Add `--live` to read from a
running Joplin as well (it takes `JOPLIN_API_TOKEN` from the environment or an
`--env-file`, only reads, and prints counts, never note content), and
`--semantic --python 3.13 --from "second-brain-joplin[semantic]==1.0.0"` to load
the embedding stack too.
