# second-brain-joplin

[![CI](https://github.com/jomkz/second-brain-joplin/actions/workflows/ci.yml/badge.svg)](https://github.com/jomkz/second-brain-joplin/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/second-brain-joplin)](https://pypi.org/project/second-brain-joplin/)

An MCP server that turns your [Joplin](https://joplinapp.org/) knowledge base into searchable memory for any MCP-capable AI client — Claude Code, Cursor, and others.

Inspired by [second-brain-mcp](https://github.com/noesskeetit/second-brain-mcp) (for Obsidian). This project covers the same use case for Joplin: your AI assistant reads, searches, and files notes directly, without leaving the tool you already use.

> **Status:** Pre-alpha — the four read tools are live; note creation is still stubbed (human-gated write lands in v0.4). See the [roadmap](#roadmap) and open issues.

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

See [docs/install.md](docs/install.md) for per-client setup guides.

---

## MCP Tools

| Tool | Description | Writes? |
|---|---|---|
| `joplin_overview` | List all notebooks with note counts | No |
| `joplin_search` | Keyword search across all notes | No |
| `joplin_read` | Read a note by ID | No |
| `joplin_recent` | Notes modified in the last N days | No |
| `joplin_semantic_search` | Find notes by meaning (embeddings) | No |
| `joplin_reindex` | Build/refresh the semantic index | No |
| `joplin_create` | Create a note (human-gated) | Yes |

> The read tools query a running Joplin instance as of v0.2. Semantic search
> (`joplin_semantic_search` / `joplin_reindex`) landed in v0.3 and needs the
> optional `[semantic]` extra (see [Semantic search](#semantic-search)).
> `joplin_create` is still stubbed; the human-gated write flow is tracked in the
> [v0.4 milestone](https://github.com/jomkz/second-brain-joplin/milestone/4).

---

## Semantic search

Semantic search finds notes by *meaning*, complementing the keyword
`joplin_search`. It embeds your notes locally and stores the vectors in a
persistent on-disk index; queries return the closest notes with a similarity
score.

It ships behind an optional extra so the base install stays light:

```bash
# Claude Code (note the quotes around the package+extra)
claude mcp add -s user second-brain-joplin \
  -e JOPLIN_API_TOKEN=your-token-here \
  -- uvx --from "second-brain-joplin[semantic]" second-brain-joplin serve
```

The default stack is [FastEmbed](https://github.com/qdrant/fastembed) (ONNX, no
PyTorch) with [`sqlite-vec`](https://github.com/asg017/sqlite-vec). You can swap
either backend via env vars (e.g. `bge-m3` via `sentence-transformers`, or a
ChromaDB store) — see [docs/semantic-search.md](docs/semantic-search.md).

Call `joplin_reindex` once to build the index (this downloads the embedding
model the first time). After that, `joplin_semantic_search` keeps the index
fresh incrementally — only notes changed since the last sync are re-embedded.

---

## vs. second-brain-mcp (Obsidian)

| | [second-brain-mcp](https://github.com/noesskeetit/second-brain-mcp) | second-brain-joplin |
|---|---|---|
| Note app | Obsidian | Joplin |
| Storage | Plain `.md` files on disk | Joplin REST API |
| Requires app running | No | Yes (Joplin + Web Clipper) |
| Semantic search | Yes (bge-m3) | Yes (FastEmbed / bge-m3) |
| Write support | Human-gated | Human-gated (v0.4) |
| Install | `uvx second-brain-mcp` | `uvx second-brain-joplin` |

---

## Notebook structure

The [PARA method](https://fortelabs.com/blog/para/) works well with Joplin. See [docs/notebook-structure.md](docs/notebook-structure.md) for a recommended setup.

---

## Roadmap

| Milestone | Theme | Status |
|---|---|---|
| [v0.1 — Bootstrap](https://github.com/jomkz/second-brain-joplin/milestone/1) | Repo, CI, package skeleton | Done |
| [v0.2 — Core Read Tools](https://github.com/jomkz/second-brain-joplin/milestone/2) | All read MCP tools working | Done |
| [v0.3 — Semantic Search](https://github.com/jomkz/second-brain-joplin/milestone/3) | Embedding index, semantic search | Done |
| [v0.4 — Write Workflow](https://github.com/jomkz/second-brain-joplin/milestone/4) | Human-gated note creation | Planned |
| [v1.0 — Publish](https://github.com/jomkz/second-brain-joplin/milestone/5) | PyPI, full docs, templates | Planned |

---

## Security & privacy

This server keeps your notes local: it talks only to Joplin's Web Clipper REST API on `localhost` and runs on your own machine. Anything an MCP client can read, the connected AI can read — so apply least privilege and don't expose notebooks with credentials or other sensitive data. Note creation is planned as an explicit human-gated flow (v0.4); v0.1 does no silent writes.

Two caveats apply once you enable semantic search: it writes a **local index** (under your XDG data dir by default) that stores note text excerpts and titles alongside the embeddings, and it downloads the embedding model **once over the network** on the first reindex. Your note *content* is embedded locally and never leaves your machine. See [SECURITY.md](SECURITY.md) for details and how to report a vulnerability.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Issues and PRs welcome — especially for testing against different Joplin versions and OS platforms.

---

## License

MIT — see [LICENSE](LICENSE).
