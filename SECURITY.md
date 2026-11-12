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
  write, especially with note creation turned on, where your approval of each
  new note is what stops such text from writing more.
- **Least privilege.** Anything an MCP client can read, the connected AI can
  read. Don't expose notebooks containing credentials, regulated data, or other
  people's private information. Apply least privilege to your notes.
- **A notebook filter.** `SBJ_NOTEBOOKS` (only these) and
  `SBJ_EXCLUDE_NOTEBOOKS` (not these) limit which notebooks any tool can see, on
  every transport
  ([how it works](docs/remote-access.md#choosing-which-notebooks-are-exposed)).
  A hidden note is left out of listings and searches, reads exactly like a note
  that doesn't exist, and is never written to the semantic index by a server
  that has the filter. A filter that doesn't match Joplin's notebooks, or a
  filter variable that is set but lists nothing, makes the server refuse to
  start, or every tool refuse if it stops matching later, never show everything.
  It filters by notebook: a visible note that quotes a hidden one still shows
  what it quotes.
- **No silent writes.** The server is read-only until you list where notes may
  be created (`SBJ_WRITE_NOTEBOOKS`); without it no write tool is registered and
  a client can't see one. With it, `joplin_create_note` adds a new note to those
  notebooks and does nothing else: it can't edit, move or delete, and it can't
  write to a notebook the filter hides. The check on each note is your client's
  approval prompt, and the call carries the note in readable form so the prompt
  shows what will be written. Keep that prompt on (in claude.ai, "Needs
  approval" rather than "Allow always"); Claude Code is told to ask on every
  call. The server can't ask you itself on every client, so it doesn't claim to:
  it limits where a note can land, logs each attempt by id, and returns the note
  already made when the same request is repeated within ten minutes
  ([Creating notes](docs/remote-access.md#creating-notes)). The semantic tools
  only read from Joplin and write to a local index (below).

### Semantic search

Semantic search (optional, via the `[semantic]` extra) changes the data
footprint in two ways worth understanding:

- **A local, unencrypted index.** Embedding your notes writes a persistent index
  on disk (`SBJ_INDEX_DIR`, by default under your XDG data directory). It stores
  the embedding vectors **plus plaintext chunk text and note titles/ids** derived
  from your notes — treat it as sensitive as the notes themselves. Stale entries
  are pruned only when you reindex, so a note deleted in Joplin can linger in the
  index until the next sync (run `joplin_reindex` to reconcile). With a notebook
  filter set, hidden notes are never indexed, one that becomes hidden is dropped
  at the next sync, and a search returns only notes that are visible at that
  moment, whatever the file holds. The file is shared by every process that
  uses the same `SBJ_INDEX_DIR`: a `second-brain-joplin reindex` run without
  the server's settings has no filter and writes every note into it, so run it
  with the server's `--env-file`.
- **A one-time model download.** The first `joplin_reindex` downloads the
  embedding model from the internet (e.g. the Hugging Face / FastEmbed CDN) and
  caches it locally. Your note *content* is embedded on your machine and is never
  sent anywhere — only the model weights are fetched.

See also the privacy considerations in
[docs/reference/second-brain-inspiration.md](docs/reference/second-brain-inspiration.md).
