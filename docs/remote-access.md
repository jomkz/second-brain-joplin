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

Every tool is read-only toward Joplin, the same over HTTP as over stdio:

- **No write tool is registered.** Note creation returns with the human-gated
  write workflow (v0.5). In Claude's connector settings you can still set any
  tool to "always ask".
- **Annotations** mark every tool read-only, except `joplin_reindex`, which
  updates the local search index only (never Joplin, never destructive).
- **Bounded arguments:** `limit` 1–50 for the searches, 1–100 for
  `joplin_recent`, `days` 1–3650. Anything outside is refused before Joplin is
  called.
- **Long notes are read in pages.** Claude caps a tool result near 150,000
  characters, so `joplin_read` returns at most `max_chars` (default 50,000, up to
  100,000) from `offset`, with `total_chars` and `next_offset` for the rest.

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
| `SBJ_RATE_LIMIT_PER_MINUTE` | `60` | Tool calls per caller; 0 = off |
| `SBJ_SYNC_INTERVAL_MINUTES` | `15` | Background index sync; 0 = off |

Plus the usual `JOPLIN_API_TOKEN`, `JOPLIN_BASE_URL` and the `SBJ_*` semantic
settings ([semantic-search.md](semantic-search.md)).
