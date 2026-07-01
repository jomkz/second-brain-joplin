# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Semantic search** (v0.3): two new MCP tools — `joplin_semantic_search` (find
  notes by meaning, returning top-k hits with similarity scores) and
  `joplin_reindex` (build/refresh the embedding index; `full=True` rebuilds from
  scratch). The index **persists** across restarts and syncs **incrementally**,
  re-embedding only notes whose Joplin `updated_time` changed and dropping deleted
  ones.
- Pluggable backends behind `Embedder` / `VectorIndex` interfaces: embedders
  **FastEmbed** (default, ONNX) or **sentence-transformers** (bge-m3), and vector
  stores **sqlite-vec** (default, single file) or **ChromaDB** — selected via
  `SBJ_EMBEDDING_BACKEND` / `SBJ_VECTOR_STORE`. Shipped as optional extras
  (`semantic`, `semantic-chroma`, `semantic-st`) so the base install stays light;
  invoking a semantic tool without the extra returns a clear, actionable error.
- New `SBJ_*` settings (`SBJ_EMBEDDING_BACKEND`, `SBJ_EMBEDDING_MODEL`,
  `SBJ_VECTOR_STORE`, `SBJ_INDEX_DIR`, `SBJ_SEMANTIC_AUTO_SYNC`) and a
  [semantic-search guide](docs/semantic-search.md).
- **PR auto-labeler** (`.github/workflows/labeler.yml`, `actions/labeler@v5`)
  applies `component:*` labels to PRs from `.github/labeler.yml` — the config is
  migrated to the v5 schema and refreshed to match the v0.2 package layout.
- **Static type checking** with `mypy` as a required CI gate (`uv run mypy src`).
- **`actionlint` pre-commit hook** lints `.github/workflows/*.yml`, catching
  workflow-syntax regressions locally (and in CI via `pre-commit run --all-files`).
- Extra pre-commit hygiene hooks (end-of-file, trailing-whitespace, YAML/TOML
  checks).

### Changed

- The server lifespan now yields an `AppContext` (Joplin client + settings) rather
  than a bare client; the semantic service is built lazily on first use so startup
  never loads a model. Read tools reach the client via `app_context(ctx).client`.
- **CI/CD re-architected around a reusable `checks` workflow.** Lint, type-check,
  the test matrix, and package build/validation now live in
  `.github/workflows/checks.yml`, invoked by both `ci.yml` (push/PR) and
  `release.yml` (before publish) — so releases can no longer ship code that
  hasn't passed the full check suite. The release job now publishes the exact
  artifact built and tested in `checks` (build-once/test/publish), with
  `skip-existing` on re-runs.
- CI now installs with `uv sync --locked` (fails on a drifted `uv.lock`), adds
  least-privilege `permissions` and `concurrency` cancellation, and validates
  packaging (`uv build` + `twine check` + wheel smoke test) on every PR.
- Lint is now driven by `pre-commit` in CI, making `.pre-commit-config.yaml` the
  single source of truth for ruff (no more version drift with the dev group).
- **mypy now runs in `strict` mode over both `src` and `tests`** (previously a
  pragmatic baseline scoped to `src`); the CI type-check step is now `uv run mypy`.

### Fixed

- Moved the `--cov-fail-under=90` gate out of pytest `addopts` into the CI
  command so running a subset of tests locally no longer spuriously fails.

## [0.2.0] — Core Read Tools

The four read tools now return real data from a running Joplin instance, on top
of a re-architected package layout.

### Added

- **Live read tools** against the Joplin Data API: `joplin_overview` (notebook
  tree with note counts), `joplin_search` (keyword search with excerpts),
  `joplin_read` (full note by ID), and `joplin_recent` (notes modified in the
  last N days, ISO-8601 timestamps).
- Typed configuration (`Settings`), a `JoplinError` exception hierarchy, and
  pydantic response models (`Note`, `Notebook`, `SearchResult`, `RecentNote`)
  that give each tool a rich MCP output schema.

### Changed

- **Package re-architected** from two flat modules into focused ones: `config`,
  `errors`, `models`, `joplin_client`, `cli`, and a `tools/` package. The CLI
  entry point moved to `second_brain_joplin.cli:main`.
- The Joplin client now owns a single shared `httpx.AsyncClient` created via the
  server lifespan (replacing the module-global singleton), follows Joplin's
  `has_more`/`page` pagination, and maps HTTP failures to typed errors that
  surface to MCP clients as `ToolError`.
- `pydantic` is now a direct dependency and `fastmcp` is pinned to `>=3,<4`.
- `joplin_create` remains a human-gated stub (issue #10), now wired through the
  new client and taking a `Context` so the confirmation flow can slot in.

## [0.1.0] — Bootstrap

Initial project skeleton — the MCP server starts and all tools are stubbed.

### Added

- `second-brain-joplin` CLI with a `serve` subcommand and `--version`.
- FastMCP server exposing five stubbed tools (`joplin_overview`,
  `joplin_search`, `joplin_read`, `joplin_recent`, `joplin_create`), each
  returning a `{"status": "not implemented"}` payload.
- `JoplinClient` skeleton with a working `ping()` against the Joplin Web Clipper
  REST API; remaining methods stubbed for v0.2.
- `.env` support via `python-dotenv` (`JOPLIN_API_TOKEN`, `JOPLIN_BASE_URL`).
- Test suite with `pytest` + `respx`, and a 90% coverage gate.
- uv-based toolchain, `uv.lock`, and CI (ruff lint + format check, pytest on
  Python 3.11/3.12/3.13).
- PyPI release workflow via OIDC trusted publishing.
- Dependabot config; pre-commit, EditorConfig, and pinned Python version.
- Documentation: install, notebook structure (PARA), project management,
  releasing runbook, security policy, and an inspiration/reference note.

[Unreleased]: https://github.com/jomkz/second-brain-joplin/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/jomkz/second-brain-joplin/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/jomkz/second-brain-joplin/releases/tag/v0.1.0
