# Remote access

`second-brain-joplin` normally runs over **stdio**, started by an MCP client on the
same machine as Joplin Desktop. Claude's **custom connectors** (claude.ai, Claude
Desktop, the mobile apps, Cowork, Claude Code) work differently: they call an MCP
server over HTTPS **from Anthropic's cloud**, not from your device. HTTP mode lets
this server be one of those connectors.

```
Claude (Anthropic's cloud)
        │  HTTPS, OAuth bearer token
        ▼
your tunnel or reverse proxy (public URL, TLS)
        │
        ▼
second-brain-joplin serve --transport http   (127.0.0.1:8775)
        │  HTTP + Joplin token, never leaves the machine
        ▼
Joplin Desktop (localhost:41184)
```

The server stays bound to loopback. Something else publishes it: a Cloudflare
Tunnel, Tailscale Funnel, or a reverse proxy with TLS. Joplin's own token never
leaves the machine.

## Running in HTTP mode

```bash
second-brain-joplin serve --transport http --public-url https://joplin.example.com
```

Every option falls back to an environment variable, then to its default:

| Flag | Env var | Default | Notes |
|---|---|---|---|
| `--transport {stdio,http}` | `SBJ_TRANSPORT` | `stdio` | stdio setups are unchanged |
| `--host` | `SBJ_HOST` | `127.0.0.1` | Loopback; the tunnel reaches it locally |
| `--port` | `SBJ_PORT` | `8775` | |
| `--path` | `SBJ_HTTP_PATH` | `/mcp` | The MCP endpoint |
| `--public-url` | `SBJ_PUBLIC_URL` | none | The server's public origin (`https://host`, no path); sign-in needs it |
| `--env-file PATH` | | none | Loads `KEY=value` lines first; variables already set win. For launchd and other service managers that can't load an env file |
| `--no-auth` | | off | No sign-in, for a local test only (below) |

The HTTP-only flags are refused with `--transport stdio`, so a typo can't
silently run the wrong mode.

### How it behaves

- **Stateless, plain JSON.** Each request stands alone and gets a JSON response.
  A restart never breaks Claude's session, and there is no long-lived event stream
  for a proxy to cut (Cloudflare drops a response that sends nothing for 125
  seconds). None of the tools sends server-initiated messages, which is all a
  stateful session would add.
- **Host check.** A request whose `Host` header isn't a loopback name or the
  public URL's host is answered `421` before it reaches MCP. This blocks DNS
  rebinding against the loopback port.
- **`/healthz`** answers `{"server": true, "joplin": true}` with `200`, or
  `"joplin": false` with `503` when Joplin Desktop isn't answering. It carries no
  note data, version or configuration, because it is never behind sign-in.
  Keep it off the public internet anyway (see your tunnel's firewall rules).

### Start-up refusals

HTTP mode refuses to start rather than expose your notes by mistake:

- **No sign-in configured** and no `--no-auth`: refused.
- **`--no-auth`** is accepted only on a loopback address and without a public URL.
  A tunnel reaches a loopback server just as well as a public one, so loopback alone
  is not a reason to skip sign-in.
- A public URL that isn't `https://host` (a path, a query, plain `http` off
  loopback) is refused, as is a port outside 1 to 65535 or a path without a
  leading `/`.

For a quick local test with no sign-in:

```bash
second-brain-joplin serve --transport http --no-auth
curl -s http://127.0.0.1:8775/healthz
```

## Sign-in

Claude's custom connectors sign in with OAuth. HTTP mode uses FastMCP's OAuth
proxy with **GitHub** as the identity provider: the proxy offers Claude the
client registration it expects (Dynamic Client Registration, or a Client ID
Metadata Document), sends you to GitHub to sign in, and then hands Claude a token
of its own. GitHub sign-in alone would admit any GitHub account, so the server
also checks every request against a list of **numeric GitHub user ids**. Ids, not
logins: a login can be renamed and then registered by someone else.

### Set it up

1. **Create a GitHub OAuth App** on your own account (GitHub → Settings →
   Developer settings → OAuth Apps → New OAuth App):
   - Homepage URL: your public URL, e.g. `https://joplin.example.com`
   - Authorization callback URL: `https://joplin.example.com/auth/callback`
   Then generate a client secret.
2. **Find your GitHub id:** `curl -s https://api.github.com/users/<login> | jq .id`.
3. **Set all four variables** (an env file passed with `--env-file`, mode 600, is
   a good home for them):

   | Variable | What |
   |---|---|
   | `SBJ_GITHUB_CLIENT_ID` | The OAuth App's client id |
   | `SBJ_GITHUB_CLIENT_SECRET` | The OAuth App's client secret |
   | `SBJ_JWT_SIGNING_KEY` | 32+ random characters: `openssl rand -base64 32` |
   | `SBJ_ALLOWED_GITHUB_IDS` | Your numeric id; several, comma-separated |

   Optional: `SBJ_OAUTH_REDIRECT_URIS`, the OAuth clients allowed to register
   (default: claude.ai's callback only, `https://claude.ai/api/mcp/auth_callback`).
4. **Start the server** with `--public-url` (or `SBJ_PUBLIC_URL`); sign-in needs it.

Set all four or none: some but not all is refused at start-up, naming what's
missing (never a value).

### What it does

- **Anyone not listed gets 401** before any MCP message is read. A second check
  runs for every tool, so a mistake in one layer doesn't open the tools.
- **Scope `read:user`:** the server only ever learns your public profile.
  (FastMCP's default, `user`, could also write it.)
- **GitHub is asked once per five minutes per token**, not on every request.
- **Registered clients survive restarts.** FastMCP keeps them in an encrypted
  store on disk (under your user data directory), keyed from
  `SBJ_JWT_SIGNING_KEY`. Rotating the GitHub client secret changes nothing for
  Claude; rotating the signing key signs every client out.
- **Consent page:** after GitHub, the server asks you to approve the client, every
  time. **Approve only a sign-in you started yourself.** claude.ai's callback is
  the same for every claude.ai user, so an authorize link someone else sends you
  could connect your notes to *their* Claude account if you approve it.

### Turning access off

The token Claude holds lasts a year (GitHub OAuth Apps issue no refresh token).
To cut access at once, do any one of:

- revoke the grant at GitHub: Settings → Applications → Authorized OAuth Apps;
- rotate `SBJ_JWT_SIGNING_KEY` and restart: every issued token stops working;
- stop the tunnel, or the server.

## What a remote client can do

Unless you turn note creation on ([Creating notes](#creating-notes)), every tool
is read-only toward Joplin, the same over HTTP as over stdio:

- **No write tool is registered** until you list where notes may go. A client
  can't call, or even see, a tool that isn't there.
- **Annotations** mark every tool read-only, except `joplin_reindex`, which
  updates the local search index only (never Joplin, never destructive), and
  `joplin_create_note`, which is marked as a write that adds and never destroys.
- **Bounded arguments:** `limit` 1–50 for the searches, 1–100 for
  `joplin_recent`, `days` 1–3650. Anything outside is refused before Joplin is
  called.
- **Long notes are read in pages.** Claude caps a tool result near 150,000
  characters, so `joplin_read` returns at most `max_chars` (default 50,000, up to
  100,000) from `offset`, with `total_chars` and `next_offset` for the rest.
- **Only the notebooks you choose**, if you set a notebook filter (next section).
  Without one, every notebook is readable.

## Choosing which notebooks are exposed

By default every notebook is readable. Over HTTP, whatever Claude reads travels
to Anthropic, so decide which notebooks that should cover. Two variables set a
filter. They apply to every tool, on stdio as well as HTTP:

| Variable | Effect |
|---|---|
| `SBJ_NOTEBOOKS` | Only these notebooks are visible |
| `SBJ_EXCLUDE_NOTEBOOKS` | These notebooks are hidden |

Each is a comma-separated list of notebook ids or titles, and an entry covers the
notebook and every notebook under it. Hiding wins: with both set, a notebook is
visible when the first list covers it and the second doesn't. Prefer ids. An id
survives a rename; a title has to match exactly and belong to one notebook only.

To find the ids, and to check a filter before a client sees through it:

```bash
second-brain-joplin notebooks
```

```
Notebook filter: 3 of 4 notebooks visible.
Note creation: allowed in the 1 marked writable.
writable  c7d1e5a09b3f4c2d8e6f1a0b9c8d7e6f  Inbox (4)
hidden    5a1f0c2e9b7d4f63a8e1c0d2b4f6a7c9  Journal (212)
visible   9c40d1e7a3b24f58b6c9e0f1a2d3b4c5  Work (57)
visible   0b7e3f9a1c2d4e5f8a7b6c5d4e3f2a1b    Projects (31)
```

It lists every notebook with its id and note count (hidden ones too: this is
your own terminal), marked under the settings it was run with: `hidden`,
`visible`, or `writable` where a note may also be created
([Creating notes](#creating-notes)). Add `--env-file` to read the settings from
the server's env file.

What a filter changes:

- **`joplin_overview`** lists visible notebooks only. A visible notebook under a
  hidden one moves to the top of the tree, so the hidden parent's name isn't shown.
- **`joplin_search` and `joplin_recent`** leave hidden notes out, and keep reading
  Joplin's results until `limit` is filled.
- **`joplin_read`** answers for a hidden note exactly as it does for a note that
  doesn't exist.
- **Semantic search** never indexes a hidden note, so its text isn't in the
  on-disk index either. A note that becomes hidden (it moved, its notebook moved,
  or you changed the filter) is dropped at the next sync, and a search always
  drops such notes before it answers.
- **It follows Joplin as it changes.** The filter is checked against Joplin's
  notebooks on every call: a new sub-notebook of a visible notebook is visible at
  once, and a note moved into a hidden notebook is gone at the next call.

A filter that doesn't match Joplin's notebooks never falls back to showing
everything:

- **At start-up**, `serve` refuses to start, naming the entry: an id no notebook
  has, a title no notebook has, a title two notebooks share, or a notebook one
  list shows and the other hides. If Joplin isn't answering at that moment there
  is nothing to check against, so the server starts and checks on every call.
- **While running** (you renamed or deleted a notebook the filter names), every
  tool refuses with a message saying the filter needs fixing. The client isn't
  told which entry, since that can be a hidden notebook's title. The server log
  and `second-brain-joplin notebooks` say.

What it doesn't do:

- It filters by notebook, not by content. A visible note that quotes or links a
  hidden one still shows what it says itself.
- A note that is in no notebook is hidden once a filter is set.
- The settings are read when the server starts, so restart it after changing
  them. An index built before the change holds the newly hidden text until the
  next sync; HTTP mode syncs at start-up, and `second-brain-joplin reindex` does
  it at once.

## Creating notes

The server is read-only until you say where notes may go:

| Variable | Effect |
|---|---|
| `SBJ_WRITE_NOTEBOOKS` | Notes may be created in these notebooks: ids or titles, comma-separated, each with its sub-notebooks. `*` means every visible notebook |

With it set, one more tool appears: `joplin_create_note(title, body, notebook)`.
It adds one new markdown note to a notebook on the list, named by its exact
title or its id. That is all it can do. It can't change, move or delete a note,
and it can't write to a notebook the filter hides. Without the variable the tool
isn't registered at all.

A notebook made for the purpose is a good first setting, for example
`SBJ_WRITE_NOTEBOOKS=Inbox`. `second-brain-joplin notebooks` marks the notebooks
that can receive notes `writable`.

### Who confirms each note

You do, in your client. The server can't put its own question to you on every
client (claude.ai's connectors don't offer that part of MCP), so the check on
each note is the client's approval prompt for the call. That is why the call
carries the whole note in readable form: the notebook by name, the title, the
text. What you approve is what gets written.

- **claude.ai and the Claude apps:** keep `joplin_create_note` on "Needs
  approval" in the connector's tool settings. Choosing "Allow always" turns the
  per-note check off: Claude can then add notes to the listed notebooks without
  asking you.
- **Claude Code:** the tool carries a flag that makes Claude Code ask on every
  call, with no "don't ask again", whatever allow rules or permission mode are in
  force.
- **Other clients:** find out how yours treats a tool that isn't read-only
  before you turn this on.

### What the server enforces

- **Where.** Only the listed notebooks, and never a hidden one. A request for any
  other notebook gets one answer, whether that notebook is hidden, doesn't exist
  or just isn't listed, followed by the notebooks that can receive notes.
- **How much.** A title of up to 300 characters, a body of up to 100,000.
- **A record.** Each created note is logged with its id, its notebook's id and
  the caller. Never its title or text:

  ```
  2026-11-12 16:40:02,113 INFO second_brain_joplin.audit: note created id=4be0…a1 notebook=c7d1…6f caller=65598
  ```
- **No second copy after a lost answer.** The tool chooses the note's id itself.
  If Joplin creates the note but its answer never arrives, the tool looks for
  that id and reports the note as created instead of failing. If it can't tell,
  it says so and asks you to look in Joplin before trying again.

A wrong `SBJ_WRITE_NOTEBOOKS` (a title no notebook has, a notebook the filter
hides) stops `serve` from starting, as a wrong filter does. If it stops matching
later, `joplin_create_note` refuses and the read tools carry on.

Notes hold text from anywhere: a clipped web page, a pasted email. Text written
to steer an AI could ask it to write more notes. The approval prompt is where you
catch that, which is the reason to keep it on.

## Limits and logs

- **Rate limit:** `SBJ_RATE_LIMIT_PER_MINUTE` tool calls per minute per GitHub
  account (default 60, 0 turns it off), as a token bucket that allows bursts of
  half that. Listing tools and protocol requests aren't counted. Over the limit,
  the call is refused with "Rate limit exceeded".
- **Semantic search** runs at most two queries at a time, so a burst can't tie
  up the embedding model.
- **Logs** go to stderr, one line per tool call:

  ```
  2026-11-11 16:40:02,113 INFO second_brain_joplin.audit: tool=joplin_search caller=65598 outcome=ok ms=41
  ```

  Never the arguments (a search query is note content), never results, never
  tokens. Two loggers that would leak are silenced in HTTP mode: httpx's request
  log (the Joplin token travels in the URL's query string, the only way Joplin's
  API accepts it) and uvicorn's access log (the sign-in callback URL carries the
  OAuth code).

## Indexing

A remote tool call has to finish quickly: claude.ai stops waiting after 240
seconds, and Cloudflare drops a response that sends nothing for 125. A first
full index of a large vault (model download plus every note) can take longer, so
indexing stays out of the request path:

- **Build it first, on the server's machine:** `second-brain-joplin reindex`
  (add `--full` to rebuild from scratch). It has no time limit.
- **Background sync:** in HTTP mode the server syncs once at start-up and then
  every `SBJ_SYNC_INTERVAL_MINUTES` (default 15, 0 turns it off). Runs never
  overlap, a failed run is logged and the next one tries again, and if semantic
  search isn't installed the loop stops quietly.
- **Over HTTP**, `joplin_reindex(full=True)` is refused with a pointer to the
  command above; incremental syncs (`full=false`) still work.

## Publishing it

The server only listens on loopback; something with TLS has to publish it at
the public URL. Three ways that work:

- **Cloudflare Tunnel** (recommended). `cloudflared` on the server's machine
  dials out, so no port is opened. Point a public hostname at
  `http://127.0.0.1:8775`, and run `cloudflared tunnel run --token-file <file>`
  as a service. Don't put Cloudflare Access in front: Claude is a machine client
  and can't complete its login. Don't use Quick Tunnels: their hostname changes
  on every start. On the Free plan, turn **Bot Fight Mode off** for the zone: it
  challenges automated clients, which Claude's calls are, and no rule can exempt
  them.
- **Tailscale Funnel**: `tailscale funnel --bg 8775` publishes it at your
  machine's `ts.net` name with a certificate, no domain needed. No firewall in
  front, and Funnel is beta.
- **A reverse proxy** (Caddy, nginx) on a host with a public address and TLS.

### A firewall in front (recommended)

Claude's requests come from Anthropic's published outbound ranges,
`160.79.104.0/21` and `153.61.208.0/20`
([Anthropic's IP addresses](https://platform.claude.com/docs/en/api/ip-addresses)).
Only three paths have to be reachable from anywhere, because your own browser
opens them while you sign in: `/authorize`, `/auth/callback` and `/consent`.
A rule that blocks everything else unless it comes from those two ranges keeps
`/mcp`, `/token`, `/register`, `/.well-known/*` and `/healthz` closed to the rest
of the internet. As a Cloudflare custom rule (action Block):

```
(http.host eq "joplin.example.com")
and not (http.request.uri.path in {"/authorize" "/auth/callback" "/consent"})
and not (ip.src in {160.79.104.0/21 153.61.208.0/20})
```

### Keeping it running

Run it under your service manager, with the secrets in a mode-600 env file.
A user LaunchAgent on macOS (`~/Library/LaunchAgents/example.second-brain-joplin.plist`;
Joplin Desktop runs in your login session, so a per-user agent is the right fit):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>example.second-brain-joplin</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/you/.local/bin/second-brain-joplin</string>
    <string>serve</string>
    <string>--transport</string><string>http</string>
    <string>--env-file</string><string>/Users/you/.config/second-brain-joplin/serve.env</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardErrorPath</key><string>/Users/you/Library/Logs/second-brain-joplin.log</string>
</dict>
</plist>
```

Or a systemd user unit on Linux (`~/.config/systemd/user/second-brain-joplin.service`):

```ini
[Unit]
Description=second-brain-joplin MCP server (HTTP mode)

[Service]
ExecStart=%h/.local/bin/second-brain-joplin serve --transport http --env-file %h/.config/second-brain-joplin/serve.env
Restart=on-failure

[Install]
WantedBy=default.target
```

Install the command with `uv tool install "second-brain-joplin[semantic]"`, and
build the index once with `second-brain-joplin reindex` before the first start.

## Adding it to Claude

1. On claude.ai: **Customize → Connectors → Add custom connector**.
2. Name it, and enter the URL: your public URL plus the path,
   `https://joplin.example.com/mcp`.
3. Claude finds the sign-in on its own. Sign in with GitHub, then approve the
   consent page.
4. Optional: in the connector's tool settings, set any tool to always ask.

Connectors you add on claude.ai also work in Claude Desktop, the mobile apps and
Cowork. Free accounts can add one custom connector.

## Environment variables at a glance

| Variable | Default | |
|---|---|---|
| `SBJ_TRANSPORT` | `stdio` | `http` for HTTP mode |
| `SBJ_HOST` / `SBJ_PORT` / `SBJ_HTTP_PATH` | `127.0.0.1` / `8775` / `/mcp` | Where it listens |
| `SBJ_PUBLIC_URL` | none | The public origin; required with sign-in |
| `SBJ_GITHUB_CLIENT_ID` / `SBJ_GITHUB_CLIENT_SECRET` | none | The GitHub OAuth App |
| `SBJ_JWT_SIGNING_KEY` | none | 32+ characters |
| `SBJ_ALLOWED_GITHUB_IDS` | none | Numeric GitHub ids allowed in |
| `SBJ_OAUTH_REDIRECT_URIS` | claude.ai's callback | OAuth clients allowed to register |
| `SBJ_NOTEBOOKS` | none | Only these notebooks (ids or titles, comma-separated) are visible |
| `SBJ_EXCLUDE_NOTEBOOKS` | none | These notebooks are hidden |
| `SBJ_WRITE_NOTEBOOKS` | none (read-only) | Notes may be created in these notebooks; `*` = every visible one |
| `SBJ_RATE_LIMIT_PER_MINUTE` | `60` | Tool calls per caller; 0 = off |
| `SBJ_SYNC_INTERVAL_MINUTES` | `15` | Background index sync; 0 = off |

Plus the usual `JOPLIN_API_TOKEN`, `JOPLIN_BASE_URL` and the `SBJ_*` semantic
settings ([semantic-search.md](semantic-search.md)).
