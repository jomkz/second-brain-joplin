# Security Policy

## Reporting a vulnerability

Please report suspected vulnerabilities privately via GitHub Security Advisories
(**Security → Report a vulnerability** on the repository) rather than opening a
public issue. We aim to acknowledge reports within a few days.

## Data handling & privacy

`second-brain-joplin` is designed to keep your notes local:

- **Local-only API.** The server talks to Joplin's Web Clipper REST API on
  `localhost` (default `http://localhost:41184`). It does not send your notes to
  any third-party service.
- **Runs on your machine.** The MCP server runs locally, launched by your MCP
  client (e.g. Claude Code). Your Joplin API token is read from the environment
  (`JOPLIN_API_TOKEN`) and is never committed — keep it out of version control.
- **Least privilege.** Anything an MCP client can read, the connected AI can
  read. Don't expose notebooks containing credentials, regulated data, or other
  people's private information. Apply least privilege to your notes.
- **No silent writes.** The v0.2 tools are read-only; the semantic tools only
  read from Joplin and write to a local index (below). Note creation is planned
  as an explicit **human-gated** flow in v0.4 — no writes to Joplin happen
  without your confirmation.

### Semantic search

Semantic search (optional, via the `[semantic]` extra) changes the data
footprint in two ways worth understanding:

- **A local, unencrypted index.** Embedding your notes writes a persistent index
  on disk (`SBJ_INDEX_DIR`, by default under your XDG data directory). It stores
  the embedding vectors **plus plaintext chunk text and note titles/ids** derived
  from your notes — treat it as sensitive as the notes themselves. Stale entries
  are pruned only when you reindex, so a note deleted in Joplin can linger in the
  index until the next sync (run `joplin_reindex` to reconcile).
- **A one-time model download.** The first `joplin_reindex` downloads the
  embedding model from the internet (e.g. the Hugging Face / FastEmbed CDN) and
  caches it locally. Your note *content* is embedded on your machine and is never
  sent anywhere — only the model weights are fetched.

See also the privacy considerations in
[docs/reference/second-brain-inspiration.md](docs/reference/second-brain-inspiration.md).
