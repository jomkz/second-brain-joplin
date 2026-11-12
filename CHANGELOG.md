# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Notebook filter** (#59): `SBJ_NOTEBOOKS` (only these) and
  `SBJ_EXCLUDE_NOTEBOOKS` (not these) limit which notebooks every tool can see,
  on stdio and HTTP alike. Entries are notebook ids or titles and cover their
  sub-notebooks; hiding wins when both are set. `joplin_overview` lists visible
  notebooks only, `joplin_search` and `joplin_recent` leave hidden notes out and
  keep reading until `limit` is filled, `joplin_read` answers for a hidden note
  exactly as for one that doesn't exist, and semantic search never writes a
  hidden note to its index. The filter is checked against Joplin on every call,
  so a moved note or a new sub-notebook takes effect at once. A filter that
  doesn't match Joplin's notebooks never shows everything instead: `serve`
  refuses to start, and every tool refuses if it stops matching later
  ([guide](docs/remote-access.md#choosing-which-notebooks-are-exposed)).
- **`second-brain-joplin notebooks`** (#59): lists every notebook with its id
  and note count, marked visible or hidden under the current filter, to find the
  ids and check a filter before a client sees through it.

### Changed

- **`joplin_read` takes Joplin ids only** (#59): `note_id` must be 32
  hexadecimal characters, the shape of every Joplin id; anything else is refused
  before Joplin is called.

### Fixed

- A semantic sync asks Joplin for its notes before it touches the index (#59),
  so a full rebuild started while Joplin is down no longer empties the index.
- `joplin_recent` stops reading Joplin's list at the first note older than
  `days` (#59) instead of always fetching `limit` notes first.

## [0.4.0] — Remote Access

Use your notes from Claude anywhere: `serve --transport http` makes the server a
Claude custom connector (claude.ai, Claude Desktop, the mobile apps, Cowork),
behind GitHub sign-in limited to the GitHub accounts you list, with a read-only,
bounded tool surface, per-caller rate limits, logs that hold no note content or
credentials, and indexing kept out of the request path. stdio use is unchanged.
Verified end to end from claude.ai and a Claude Duet task through a Cloudflare
Tunnel ([remote access guide](docs/remote-access.md)).

### Added

- **Streamable HTTP transport** (#51): `serve --transport http` runs the server
  over FastMCP's streamable HTTP, stateless with plain JSON responses, bound to
  `127.0.0.1:8775` by default, so a Claude custom connector can reach it through
  a tunnel. Flags `--host`, `--port`, `--path`, `--public-url` and `--env-file`
  fall back to `SBJ_*` variables; stdio stays the default. A strict Host check
  answers unknown hosts with 421, and `/healthz` reports only whether the server
  and Joplin are up. HTTP mode refuses to start without sign-in, except with
  `--no-auth` on a loopback address for local testing
  ([remote access guide](docs/remote-access.md)).
- **GitHub sign-in with an id allowlist** (#52): HTTP mode signs in through
  FastMCP's OAuth proxy with GitHub upstream, which gives Claude's connectors
  the Dynamic Client Registration and Client ID Metadata Documents they expect.
  Only the numeric GitHub user ids in `SBJ_ALLOWED_GITHUB_IDS` get in (anyone
  else gets 401, and a second check runs per tool); scope `read:user`;
  verification cached for five minutes; only claude.ai's callback may register
  (`SBJ_OAUTH_REDIRECT_URIS` to change it); an explicit `SBJ_JWT_SIGNING_KEY` so
  a client-secret rotation doesn't sign Claude out. Partial or malformed sign-in
  settings are refused at start-up, naming what's wrong without printing values.
- **Paged `joplin_read`** (#53): `offset` and `max_chars` (default 50,000, at
  most 100,000 characters) with `total_chars` and `next_offset` in the result,
  so a long note is read in pages instead of overflowing a client's result cap.
- **Rate limit and safe logging** (#54): tool calls are limited per GitHub
  account (`SBJ_RATE_LIMIT_PER_MINUTE`, default 60, bursts of half; listing
  tools isn't counted), semantic searches run at most two at a time, and each
  tool call logs one line (tool, caller id, outcome, duration) with no
  arguments, results or credentials. httpx's request log, which would print the
  Joplin token from the URL, and uvicorn's access log, which would print the
  OAuth code, are off in HTTP mode.
- **`reindex` subcommand and background sync** (#55):
  `second-brain-joplin reindex [--full]` builds or syncs the semantic index from
  the command line, with no time limit. In HTTP mode the server syncs the index
  at start-up and then every `SBJ_SYNC_INTERVAL_MINUTES` (default 15, 0 = off),
  never overlapping and carrying on after a failed run; and `joplin_reindex(full=True)`
  is refused there with a pointer to the CLI, since a full rebuild can outlast a
  remote tool call.
- **Remote access guide** (#56): [docs/remote-access.md](docs/remote-access.md)
  covers HTTP mode, sign-in, limits and logs, indexing, publishing the server
  (Cloudflare Tunnel, Tailscale Funnel, a reverse proxy; a firewall rule for
  Anthropic's ranges), running it as a launchd or systemd service, and adding
  it to Claude.
- CI runs the test suite on macOS too, as a separate job.
- **Tool annotations** (#53): every tool declares its side effects (read-only;
  `joplin_reindex` updates the local index only, idempotent, non-destructive).

### Changed

- **Bounded arguments** (#53): `limit` is 1–50 for the searches and 1–100 for
  `joplin_recent`, `days` 1–3650; out-of-range values are refused before Joplin
  is called.

### Removed

- The `joplin_create` stub (#53) is no longer registered on any transport; it
  returns with the human-gated write workflow (v0.5, #10).

### Fixed

- The Joplin health check counts a timeout or dropped connection as "down"
  instead of raising.
- A Joplin timeout or dropped connection during a tool call is now a clear
  "Joplin didn't answer" / "unreachable" tool error (#53), not a stack trace.

## [0.3.0] — Semantic Search

Find notes by meaning, not only by keyword: an embedding index that persists and
syncs incrementally, behind optional extras so the base install stays light.
Also the move to FastMCP 4.1, a stricter CI, and GitHub Releases on tags.

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
- **GitHub Releases** (#24): a version tag now also creates a GitHub Release,
  after the PyPI publish, with notes from that version's CHANGELOG section and
  the tested sdist and wheel attached. Pre-release versions are marked as such,
  and re-running updates the release in place (`scripts/github-release.sh`,
  which also backfills older tags).

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
- **Roadmap:** remote access is now milestone v0.4; the human-gated write
  workflow moves to v0.5.
- **FastMCP 4.1** (from 3.4), on the MCP Python SDK 2: the current FastMCP line,
  which carries the OAuth and Host-check security fixes that remote access
  builds on. Tools and settings are unchanged; every locked dependency was
  refreshed once.

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

[Unreleased]: https://github.com/jomkz/second-brain-joplin/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/jomkz/second-brain-joplin/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/jomkz/second-brain-joplin/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/jomkz/second-brain-joplin/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/jomkz/second-brain-joplin/releases/tag/v0.1.0
