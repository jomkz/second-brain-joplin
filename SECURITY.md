# Security Policy

## Reporting a vulnerability

Please report suspected vulnerabilities privately via GitHub Security Advisories
(**Security → Report a vulnerability** on the repository) rather than opening a
public issue. We aim to acknowledge reports within a few days.

## Data handling & privacy

`second-brain-joplin` keeps your notes on your machine unless you choose HTTP mode:

- **Joplin stays local.** The server talks to Joplin's Web Clipper REST API on
  `localhost` (default `http://localhost:41184`). The Joplin API token is read from
  the environment (`JOPLIN_API_TOKEN`), never leaves the machine, and is never
  committed — keep it out of version control.
- **stdio (the default) is local only.** The server is launched by an MCP client
  on the same machine (e.g. Claude Code) and talks to nothing else. What the AI
  client then does with what it reads is that client's business.
- **HTTP mode reaches the internet, deliberately.** `serve --transport http`
  (see [docs/remote-access.md](docs/remote-access.md)) lets a Claude custom
  connector call the server from Anthropic's cloud. Note content a tool returns
  then travels to Anthropic over HTTPS, the same as anything else you show Claude.
  The protections, in order:
  - The server binds to loopback; a tunnel or reverse proxy you run publishes it.
  - **GitHub sign-in, limited to listed numeric GitHub ids**
    (`SBJ_ALLOWED_GITHUB_IDS`): any other account gets 401 before a tool runs,
    and a second check runs again for every tool. HTTP mode refuses to start
    without sign-in, except `--no-auth` on loopback for a local test.
  - Only claude.ai's OAuth callback may register as a client by default. That
    callback is shared by every claude.ai user, so approve the server's consent
    page only for a sign-in you started yourself.
  - A strict Host check (421 for unknown hosts) against DNS rebinding.
  - A rate limit per GitHub account, and a cap on concurrent semantic searches.
  - Logs record each tool call's name, caller id, outcome and duration, never
    arguments, results or credentials; the HTTP client and access logs that
    would print the Joplin token or an OAuth code are silenced.
  - Put a firewall in front where you can: Claude's requests come from
    Anthropic's published outbound ranges, and only the browser sign-in pages
    need to be reachable from anywhere.
- **Token lifetime.** A GitHub OAuth App issues no refresh token, so the token
  FastMCP gives Claude lasts a year. To cut access at once, do any of: revoke the
  app's grant at GitHub (Settings → Applications → Authorized OAuth Apps), rotate
  `SBJ_JWT_SIGNING_KEY` (every issued token stops working), or stop the tunnel.
- **Notes are untrusted input to the AI.** A note can hold text from anywhere
  (web clippings, pasted email). Claude reads it as data, but text written to
  steer an AI is still text an AI reads: keep that in mind for notes you didn't
  write, especially once write tools exist.
- **Least privilege.** Anything an MCP client can read, the connected AI can
  read. Don't expose notebooks containing credentials, regulated data, or other
  people's private information. Apply least privilege to your notes.
- **A notebook filter.** `SBJ_NOTEBOOKS` (only these) and
  `SBJ_EXCLUDE_NOTEBOOKS` (not these) limit which notebooks any tool can see, on
  every transport
  ([how it works](docs/remote-access.md#choosing-which-notebooks-are-exposed)).
  A hidden note is left out of listings and searches, reads exactly like a note
  that doesn't exist, and is never written to the semantic index. A filter that
  doesn't match Joplin's notebooks makes the server refuse to start, or every
  tool refuse if it stops matching later, never show everything. It filters by
  notebook: a visible note that quotes a hidden one still shows what it quotes.
- **No silent writes.** The v0.2 tools are read-only; the semantic tools only
  read from Joplin and write to a local index (below). Note creation is planned
  as an explicit **human-gated** flow in v0.5 — no writes to Joplin happen
  without your confirmation.

### Semantic search

Semantic search (optional, via the `[semantic]` extra) changes the data
footprint in two ways worth understanding:

- **A local, unencrypted index.** Embedding your notes writes a persistent index
  on disk (`SBJ_INDEX_DIR`, by default under your XDG data directory). It stores
  the embedding vectors **plus plaintext chunk text and note titles/ids** derived
  from your notes — treat it as sensitive as the notes themselves. Stale entries
  are pruned only when you reindex, so a note deleted in Joplin can linger in the
  index until the next sync (run `joplin_reindex` to reconcile). With a notebook
  filter set, hidden notes are never indexed, and one that becomes hidden is
  dropped at the next sync or the next semantic search, whichever comes first.
- **A one-time model download.** The first `joplin_reindex` downloads the
  embedding model from the internet (e.g. the Hugging Face / FastEmbed CDN) and
  caches it locally. Your note *content* is embedded on your machine and is never
  sent anywhere — only the model weights are fetched.

See also the privacy considerations in
[docs/reference/second-brain-inspiration.md](docs/reference/second-brain-inspiration.md).
