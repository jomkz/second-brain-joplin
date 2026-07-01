# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
- TestPyPI release workflow via OIDC trusted publishing.
- Dependabot config; pre-commit, EditorConfig, and pinned Python version.
- Documentation: install, notebook structure (PARA), project management,
  releasing runbook, security policy, and an inspiration/reference note.

[Unreleased]: https://github.com/jomkz/second-brain-joplin/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/jomkz/second-brain-joplin/releases/tag/v0.1.0
