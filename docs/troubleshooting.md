# Troubleshooting

Start with two checks. They settle most problems:

```bash
curl http://localhost:41184/ping        # Joplin: answers JoplinClipperServer
uvx second-brain-joplin --version       # the server: prints its version
```

- [The client can't start the server](#the-client-cant-start-the-server)
- [A tool answers with an error](#a-tool-answers-with-an-error)
- [Notes are missing or out of date](#notes-are-missing-or-out-of-date)
- [Semantic search](#semantic-search)
- [Creating notes](#creating-notes)
- [HTTP mode](#http-mode)
- [Where the logs are](#where-the-logs-are)

## The client can't start the server

**"Command not found", or `spawn uvx ENOENT`.** The client can't find `uvx`. A
desktop app doesn't get the search path your terminal has. Give the client the
full path as its command: `which uvx` prints it on macOS and Linux, `where uvx`
on Windows.

**The first start times out.** `uvx` downloads the server the first time it
runs, and a client may stop waiting before that finishes. Run
`uvx second-brain-joplin --version` in a terminal once, then start the client
again. With semantic search, run the client's full command once the same way:
that download is larger.

**`--version` prints `0.2.0`, or the semantic tools and HTTP mode are missing.**
You asked for `[semantic]` on Python 3.15, which the embedding runtime doesn't
support yet, and the installer fell back to an old release. Add `--python 3.13`
to the `uvx` command ([Which Python](install.md#which-python)).

**The install fails naming `onnxruntime` and "no wheels with a matching Python
ABI tag".** The same cause, reported honestly because you named a version. The
same fix.

**An old version keeps starting after a new release.** `uvx` keeps the copy it
first installed ([Updating](install.md#updating)).

## A tool answers with an error

**"Joplin is unreachable at … — is Joplin Desktop running with the Web Clipper
service enabled?"** Nothing is listening at Joplin's address.

- Start Joplin Desktop. It can be minimised, but it has to be running.
- Turn the service on: **Tools → Options → Web Clipper → Enable Web Clipper
  Service**.
- If you changed the port in Joplin, set `JOPLIN_BASE_URL` to match.

**"Joplin didn't answer at … within 10 seconds".** Joplin is there and didn't
answer in time. Right after you enable the Web Clipper service, or while Joplin
is starting or busy with a large sync, this can last a minute. Try again.

**"Joplin rejected the request — check that JOPLIN_API_TOKEN is set …".** The
token is missing or isn't the one Joplin shows.

- Copy it again from the Web Clipper page in Joplin's options.
- Make sure it is in the `env` block of the client's configuration. A variable
  exported in your terminal doesn't reach a server that a desktop app starts.
- Restart the client after changing it.

**"The requested Joplin resource was not found."** No note has that id, or a
[notebook filter](configuration.md#notebooks) hides it.

**"The server's notebook settings … don't match Joplin's notebooks".** A
notebook named in `SBJ_NOTEBOOKS`, `SBJ_EXCLUDE_NOTEBOOKS` or
`SBJ_WRITE_NOTEBOOKS` was renamed, deleted or duplicated. The tools refuse
rather than guess. On the server's machine, run:

```bash
second-brain-joplin notebooks            # add --env-file <file> if the server uses one
```

It names the entry that is wrong and lists every notebook's id. Fix the setting
and restart the server. Ids don't break when a notebook is renamed.

**The server won't start, with "set, but lists no notebook".** A filter
variable is set to nothing (`SBJ_NOTEBOOKS=`). Give it a notebook, or remove the
variable to have no filter.

**"Input should be less than or equal to …" or "String should match
pattern …".** An argument was refused before Joplin was asked. The first is a
number outside its range, for example `limit` above 50. The second is
`joplin_read` given something that isn't a note id: it takes the 32-character
id that a search returns, not a title. The ranges are in [tools.md](tools.md).

## Notes are missing or out of date

**A note you wrote on another device isn't there.** The server reads the Joplin
on its own machine. A note from your phone appears once that Joplin has synced,
which it does every few minutes. Synchronise it by hand to see the note now.

**A keyword search misses a note you know exists.** `joplin_search` is Joplin's
own search and follows [its rules](https://joplinapp.org/help/apps/search): it
matches whole words. Search for `remodel*` to match "remodelling", put a phrase
in double quotes, or use `joplin_semantic_search`, which matches by meaning.

**A whole notebook is missing.** It is hidden by `SBJ_NOTEBOOKS` or
`SBJ_EXCLUDE_NOTEBOOKS`. `second-brain-joplin notebooks` shows which notebooks
are visible.

**A note outside every notebook is missing.** Once a filter is set, a note that
is in no notebook is hidden.

## Semantic search

**"Semantic search needs the optional 'fastembed' dependency".** The server was
started without the `[semantic]` install. Use the semantic form of the command
([install.md](install.md#options)).

**The first search or reindex takes minutes, or the client gives up.** The
first run downloads the embedding model and embeds every note. Do it once in a
terminal, where nothing times out:

```bash
uvx --python 3.13 --from "second-brain-joplin[semantic]" second-brain-joplin reindex
```

Give it the same `JOPLIN_API_TOKEN` and notebook settings as the server (an
`--env-file` does that). Later syncs embed only the notes that changed.

**It needs the internet once.** The model is downloaded on first use and kept.
After that, semantic search works offline.

**Results don't include a recent note.** With `SBJ_SEMANTIC_AUTO_SYNC=false` a
search doesn't sync first. Over stdio the index then changes only when you call
`joplin_reindex` or run `reindex`. In HTTP mode it is also synced in the
background every `SBJ_SYNC_INTERVAL_MINUTES` (15 by default), so a new note can
take that long to appear.

**Starting over.** The index can always be rebuilt from Joplin. Stop the
server, delete the index directory
([`SBJ_INDEX_DIR`](configuration.md#semantic-search)) and run `reindex`.

## Creating notes

**The assistant has no `joplin_create_note` tool.** The tool exists only when
`SBJ_WRITE_NOTEBOOKS` is set. After setting it, restart the server and reconnect
the client: a client reads the list of tools when it connects, and a chat that
was already open keeps the old list.

**"A note can't be created in that notebook."** The notebook isn't on the list
in `SBJ_WRITE_NOTEBOOKS`, or the filter hides it. The answer names the notebooks
that can take notes. A title has to match exactly; when two writable notebooks
share a title, name the one you mean by its id.

**The assistant created a note without asking you.** The approval prompt
belongs to your client. In claude.ai, set `joplin_create_note` back to **Needs
approval** in the connector's tool settings; **Allow always** turns the prompt
off ([Who confirms each note](remote-access.md#who-confirms-each-note)).

**"The note may or may not have been created".** Joplin took the request and
didn't answer. Look in Joplin, or ask again: the same note asked for within ten
minutes isn't created twice.

**The new note isn't on your other devices.** It is created in the Joplin on the
server's machine and reaches the others at that Joplin's next sync.

## HTTP mode

Check the server from its own machine first:

```bash
curl -s http://127.0.0.1:8775/healthz
```

`{"server":true,"joplin":true}` means both are up. `"joplin":false` (with status
503) means the server runs and Joplin isn't answering. No answer means the
server isn't running: look at its log.

**The server refuses to start.** HTTP mode won't start in a state that could
expose your notes. The message says which:

| Message | What to do |
|---|---|
| `HTTP mode needs GitHub sign-in configured` | Set the four sign-in variables ([Sign-in](remote-access.md#sign-in)), or add `--no-auth` for a test on your own machine |
| `sign-in is only partly configured: set …` | Set the variables it names. It is all four or none |
| `sign-in needs the server's public URL` | Set `SBJ_PUBLIC_URL` or `--public-url` |
| `SBJ_JWT_SIGNING_KEY must be at least 32 characters` | Make a new one: `openssl rand -base64 32` |
| `SBJ_ALLOWED_GITHUB_IDS takes numeric GitHub user ids, not logins` | Use the number that `https://api.github.com/users/<login>` shows as `id` |
| `the public URL must be the server's origin only` or `must use https` | Give `https://host` with no path |
| `--no-auth is for local testing only` or `can't be combined with a public URL` | `--no-auth` works only on a loopback address without a public URL |
| `… only apply to --transport http` | An HTTP option was given without `--transport http` |
| `--no-auth was given but sign-in is configured; drop one` | Remove `--no-auth`, or the sign-in variables |
| `… must be a number` or `must be 0 (off) or more` | `SBJ_PORT`, `SBJ_RATE_LIMIT_PER_MINUTE` or `SBJ_SYNC_INTERVAL_MINUTES` isn't a whole number in range |
| `SBJ_OAUTH_REDIRECT_URIS must be https URLs` | Every entry has to start with `https://` |
| `--env-file … does not exist or is not a file` | The path is wrong, or the service can't read it |

**Requests get `421`.** The request named a host the server doesn't expect.
`SBJ_PUBLIC_URL` has to be the exact host name your tunnel or proxy publishes.

**Signing in works, then Claude gets `401`.** The GitHub account isn't in
`SBJ_ALLOWED_GITHUB_IDS`. The server's log says so, with the account's id.

**Claude can't connect, or the sign-in page doesn't open.** Something in front
of the server is turning Claude or your browser away:

- The paths `/authorize`, `/auth/callback` and `/consent` must be reachable from
  anywhere, because your own browser opens them.
- On Cloudflare, Bot Fight Mode has to be off for the zone, and Cloudflare
  Access must not sit in front: Claude can't pass either.

See [Publishing it](remote-access.md#publishing-it).

**Is it the tunnel or the server?** Behind a Cloudflare Tunnel, ask the public
address for a page that needs no sign-in:

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://joplin.example.com/authorize
```

`400` means the server answered (it is only missing the sign-in details a real
client sends). `502` means the tunnel is up and the server isn't. `530` means
the tunnel is down.

**Every client was signed out.** `SBJ_JWT_SIGNING_KEY` changed. Sign in again.

**A new tool or setting doesn't show up in Claude.** Claude reads the tool list
when a chat connects. Start a new chat, or disconnect and reconnect the
connector.

**"Rate limit exceeded for client: …".** Too many tool calls at once: the limit
is `SBJ_RATE_LIMIT_PER_MINUTE` calls a minute (60 by default), and a burst may
be half of that. Wait a moment, or raise it.

**"A full rebuild can take longer than a remote tool call may run".** Run
`second-brain-joplin reindex --full --env-file <the server's env file>` on the
server's machine.

**On macOS, the server takes minutes to start after an upgrade.** A LaunchAgent
whose `ProcessType` is `Background` is slowed down by macOS, and the first start
after an install has many files to prepare. Leave `ProcessType` out, or install
with `uv tool install --compile-bytecode` so that work is done at install time.

**Nothing runs after a restart of the machine.** A LaunchAgent or a systemd user
unit starts when you log in, and Joplin Desktop needs your session too.

## Where the logs are

The server writes its log to standard error.

- **Claude Code:** `/mcp` shows each server's state; start with `claude --debug`
  to see what the server prints.
- **Claude Desktop:** one log per server, `mcp-server-second-brain-joplin.log`,
  in `~/Library/Logs/Claude` on macOS and `%APPDATA%\Claude\logs` on Windows.
- **HTTP mode:** wherever your service manager sends standard error. One line
  per tool call says which tool, who called, the outcome and how long it took:

  ```
  2026-11-12 16:40:02,113 INFO second_brain_joplin.audit: tool=joplin_search caller=65598 outcome=ok ms=41
  ```

The logs never hold a note's title or text, a search query or a token
([Limits and logs](remote-access.md#limits-and-logs)).

## Still stuck

[Open an issue](https://github.com/jomkz/second-brain-joplin/issues) with the
output of `second-brain-joplin --version`, your operating system, the client you
use and the error as the tool gave it. Leave your Joplin token and your notes
out of it.
