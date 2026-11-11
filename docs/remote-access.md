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
- **Consent page:** after GitHub, the server asks you to approve the client once.

### Turning access off

The token Claude holds lasts a year (GitHub OAuth Apps issue no refresh token).
To cut access at once, do any one of:

- revoke the grant at GitHub: Settings → Applications → Authorized OAuth Apps;
- rotate `SBJ_JWT_SIGNING_KEY` and restart: every issued token stops working;
- stop the tunnel, or the server.
