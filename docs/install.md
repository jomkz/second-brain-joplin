# Installation

> This document is a stub. Full setup guide is tracked in GitHub issue T6.

## Prerequisites

- Joplin Desktop installed and running
- Web Clipper service enabled: **Tools → Options → Web Clipper → Enable Web Clipper Service**
- API token copied from that same settings panel
- Python ≥ 3.11 or `uvx` (recommended)

## Claude Code

```bash
claude mcp add -s user second-brain-joplin \
  -e JOPLIN_API_TOKEN=your-token-here \
  -- uvx second-brain-joplin serve
```

## Cursor / other MCP clients

See client documentation for MCP server configuration. Use:

- **Command**: `uvx second-brain-joplin serve`
- **Env**: `JOPLIN_API_TOKEN=your-token-here`
- **Env**: `JOPLIN_BASE_URL=http://localhost:41184` (default, change only if customized)

## Semantic search (optional)

Semantic search needs the `[semantic]` extra. Point the command at the extra:

- **Command**: `uvx --from "second-brain-joplin[semantic]" second-brain-joplin serve`

Optional `SBJ_*` env vars tune the backends (all have sensible defaults):

- `SBJ_EMBEDDING_BACKEND` — `fastembed` (default) or `sentence-transformers`
- `SBJ_EMBEDDING_MODEL` — model id override (empty = backend default)
- `SBJ_VECTOR_STORE` — `sqlite-vec` (default) or `chroma`
- `SBJ_INDEX_DIR` — index location (default: under your XDG data dir)
- `SBJ_SEMANTIC_AUTO_SYNC` — re-sync before each search (`true`/`false`)

For `chroma` also install `[semantic-chroma]`; for `sentence-transformers`
(bge-m3) also install `[semantic-st]`. See
[semantic-search.md](semantic-search.md) for details.
