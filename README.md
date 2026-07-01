# second-brain-joplin

An MCP server that turns your [Joplin](https://joplinapp.org/) knowledge base into searchable memory for any MCP-capable AI client — Claude Code, Cursor, and others.

Inspired by [second-brain-mcp](https://github.com/noesskeetit/second-brain-mcp) (for Obsidian). This project covers the same use case for Joplin: your AI assistant reads, searches, and files notes directly, without leaving the tool you already use.

> **Status:** Pre-alpha — MCP tools are stubbed. See the [roadmap](#roadmap) and open issues.

---

## How it works

Joplin Desktop exposes a local REST API on `localhost:41184` (the Web Clipper service). This server wraps that API as MCP tools, so your AI client can query and update your notes in real time — no export step, no sync lag.

```
Claude Code / Cursor
       │  MCP
       ▼
second-brain-joplin (this server)
       │  HTTP + token
       ▼
Joplin Desktop (localhost:41184)
       │
       ▼
Your notes
```

---

## Prerequisites

- **Joplin Desktop** running with the Web Clipper service enabled:  
  **Tools → Options → Web Clipper → Enable Web Clipper Service**
- **API token** — copy it from the Web Clipper settings panel
- **Python ≥ 3.11** or [`uvx`](https://docs.astral.sh/uv/) (recommended — no install needed)

---

## Quickstart

### Claude Code

```bash
claude mcp add -s user second-brain-joplin \
  -e JOPLIN_API_TOKEN=your-token-here \
  -- uvx second-brain-joplin serve
```

### Other MCP clients

| Setting | Value |
|---|---|
| Command | `uvx second-brain-joplin serve` |
| `JOPLIN_API_TOKEN` | token from Joplin Web Clipper settings |
| `JOPLIN_BASE_URL` | `http://localhost:41184` (default) |

See [docs/INSTALL.md](docs/INSTALL.md) for per-client setup guides.

---

## MCP Tools

| Tool | Description | Writes? |
|---|---|---|
| `joplin_overview` | List all notebooks with note counts | No |
| `joplin_search` | Keyword search across all notes | No |
| `joplin_read` | Read a note by ID | No |
| `joplin_recent` | Notes modified in the last N days | No |
| `joplin_create` | Create a note (human-gated) | Yes |

> All tools are stubbed in v0.1. Implementation tracked in [v0.2 milestone](https://github.com/jomkz/second-brain-joplin/milestone/2).

---

## vs. second-brain-mcp (Obsidian)

| | [second-brain-mcp](https://github.com/noesskeetit/second-brain-mcp) | second-brain-joplin |
|---|---|---|
| Note app | Obsidian | Joplin |
| Storage | Plain `.md` files on disk | Joplin REST API |
| Requires app running | No | Yes (Joplin + Web Clipper) |
| Semantic search | Yes (bge-m3) | Planned (v0.3) |
| Write support | Human-gated | Human-gated (v0.4) |
| Install | `uvx second-brain-mcp` | `uvx second-brain-joplin` |

---

## Notebook structure

The [PARA method](https://fortelabs.com/blog/para/) works well with Joplin. See [docs/NOTEBOOK-STRUCTURE.md](docs/NOTEBOOK-STRUCTURE.md) for a recommended setup.

---

## Roadmap

| Milestone | Theme | Status |
|---|---|---|
| [v0.1 — Bootstrap](https://github.com/jomkz/second-brain-joplin/milestone/1) | Repo, CI, package skeleton | In progress |
| [v0.2 — Core Read Tools](https://github.com/jomkz/second-brain-joplin/milestone/2) | All read MCP tools working | Planned |
| [v0.3 — Semantic Search](https://github.com/jomkz/second-brain-joplin/milestone/3) | Embedding index, semantic search | Planned |
| [v0.4 — Write Workflow](https://github.com/jomkz/second-brain-joplin/milestone/4) | Human-gated note creation | Planned |
| [v1.0 — Publish](https://github.com/jomkz/second-brain-joplin/milestone/5) | PyPI, full docs, templates | Planned |

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Issues and PRs welcome — especially for testing against different Joplin versions and OS platforms.

---

## License

MIT — see [LICENSE](LICENSE).
