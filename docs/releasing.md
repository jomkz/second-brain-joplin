# Releasing

Releases are published to **TestPyPI** by the
[`release`](../.github/workflows/release.yml) workflow using an OIDC
**trusted publisher** — no API tokens are stored in the repo.

## One-time operator setup

Configure the trusted publisher on TestPyPI before the first upload:

1. Sign in at <https://test.pypi.org>.
2. Under **Publishing → Add a pending publisher** (or the project's Publishing
   settings once it exists), add a GitHub publisher with:
   - **Owner**: `jomkz`
   - **Repository**: `second-brain-joplin`
   - **Workflow name**: `release.yml`
   - **Environment**: `testpypi`
3. Ensure a GitHub Actions environment named `testpypi` exists on the repo
   (Settings → Environments). The workflow references it.

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
3. The workflow runs `uv build`, validates metadata with `twine check`, and
   publishes the sdist + wheel to TestPyPI.

## Verify

Install from TestPyPI and confirm the server starts:

```bash
uvx --index-url https://test.pypi.org/simple/ \
    --index https://pypi.org/simple/ \
    second-brain-joplin serve
```

> The extra `--index` lets `uvx` resolve runtime dependencies from the real
> PyPI while pulling `second-brain-joplin` itself from TestPyPI.

Production PyPI publishing is tracked for v1.0 (issue #11).
