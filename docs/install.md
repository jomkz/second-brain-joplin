# Installation

`second-brain-joplin` runs on the same computer as Joplin Desktop and is started
by your AI client. Setting it up takes three steps: turn on Joplin's local API,
check that the server starts, and add it to your client.

It is tested on Linux, macOS and Windows.

To reach your notes from claude.ai or the Claude mobile apps instead, see
[remote-access.md](remote-access.md).

## 1. Turn on Joplin's local API

1. In Joplin Desktop open **Tools → Options → Web Clipper** (on macOS,
   **Joplin → Settings → Web Clipper**).
2. Choose **Enable Web Clipper Service**.
3. On the same page, under **Advanced options**, copy the **authorisation
   token**. This is your `JOPLIN_API_TOKEN`.

The token gives full access to your notes. Keep it out of files you share or
commit.

To check that Joplin is listening:

```bash
curl http://localhost:41184/ping
```

It answers `JoplinClipperServer`. Joplin Desktop has to be running whenever you
use the server.

## 2. Check that the server starts

The simplest way to run it is [`uvx`](https://docs.astral.sh/uv/), which comes
with uv. It downloads the server on first use and needs no install step:

```bash
uvx second-brain-joplin --version
```

If you'd rather not use uv, see [Other ways to install](#other-ways-to-install).

## 3. Add it to your client

Every client needs the same three things: the command `uvx`, the arguments
`second-brain-joplin serve`, and your token in `JOPLIN_API_TOKEN`.

### Claude Code

```bash
claude mcp add -s user second-brain-joplin \
  -e JOPLIN_API_TOKEN=your-token-here \
  -- uvx second-brain-joplin serve
```

`-s user` makes it available in all your projects. Leave it out to add it to
the current project only. Don't use `-s project`: that writes the token into a
`.mcp.json` meant to be committed. Check it with `claude mcp list`, or `/mcp`
inside Claude Code.

### Claude Desktop

Open **Settings → Developer → Edit Config**, which opens
`claude_desktop_config.json`:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

Add the server under `mcpServers`, then quit and reopen Claude Desktop:

```json
{
  "mcpServers": {
    "second-brain-joplin": {
      "command": "uvx",
      "args": ["second-brain-joplin", "serve"],
      "env": {
        "JOPLIN_API_TOKEN": "your-token-here"
      }
    }
  }
}
```

### Cursor

Put the same entry in `~/.cursor/mcp.json` (every project) or `.cursor/mcp.json`
(one project):

```json
{
  "mcpServers": {
    "second-brain-joplin": {
      "type": "stdio",
      "command": "uvx",
      "args": ["second-brain-joplin", "serve"],
      "env": {
        "JOPLIN_API_TOKEN": "your-token-here"
      }
    }
  }
}
```

### Any other client

Any client that can start a local (stdio) MCP server works. Give it:

| Setting | Value |
|---|---|
| Command | `uvx` |
| Arguments | `second-brain-joplin`, `serve` |
| Environment | `JOPLIN_API_TOKEN` = your token |

If the client can't find `uvx`, give it the full path
([troubleshooting](troubleshooting.md#the-client-cant-start-the-server)).

### Try it

Ask your assistant "which notebooks do I have in Joplin?". It should call
`joplin_overview` and list them. [tools.md](tools.md) describes every tool.

## Options

Each of these is a setting in the same `env` block. All of them are listed in
[configuration.md](configuration.md).

**Limit which notebooks the assistant can see.** By default it can read every
notebook.

```json
"env": {
  "JOPLIN_API_TOKEN": "your-token-here",
  "SBJ_EXCLUDE_NOTEBOOKS": "Journal,Finances"
}
```

Use `SBJ_NOTEBOOKS` instead to name the only notebooks it may see. See
[Choosing which notebooks are exposed](remote-access.md#choosing-which-notebooks-are-exposed).

**Let it add notes.** The server is read-only until you name the notebooks that
may receive new notes:

```json
"SBJ_WRITE_NOTEBOOKS": "Inbox"
```

It can then add a note there and do nothing else. Whether you are asked before
each note is up to your client: Claude Code always asks, and elsewhere keep the
tool set to ask every time
([Who confirms each note](remote-access.md#who-confirms-each-note)).

**Search by meaning.** Semantic search is an optional install. Change the
command's arguments to:

```json
"args": ["--python", "3.13", "--from", "second-brain-joplin[semantic]", "second-brain-joplin", "serve"]
```

or, for Claude Code:

```bash
claude mcp add -s user second-brain-joplin \
  -e JOPLIN_API_TOKEN=your-token-here \
  -- uvx --python 3.13 --from "second-brain-joplin[semantic]" second-brain-joplin serve
```

Then build the index once. See [semantic-search.md](semantic-search.md).

## Which Python

You don't need to install Python yourself: `uvx` finds one, or downloads one.

- **The server** runs on Python 3.11 to 3.15.
- **Semantic search** runs on Python 3.11 to 3.14. Its embedding runtime
  (`onnxruntime`) has no build for Python 3.15 yet (November 2026).

That second line is why the semantic commands above say `--python 3.13`. Without
it, on a computer whose own Python is 3.15, the install fails with an error
naming `onnxruntime`. `--python 3.13` makes `uvx` fetch a Python that everything
supports.

If you set semantic search up before 12 November 2026, check what you are
running: until then the same command did not fail on Python 3.15 but installed
0.2.0, a release from before semantic search existed, and said so only in a
one-line warning that a client never shows. The sign is `--version` printing
`0.2.0`, with no semantic tools and no HTTP mode. Those old releases have since
been withdrawn, so it can't happen to a new install.

## Updating

`uvx` installs the newest release the first time and then keeps using that copy.
To move to a newer release, either name the version you want:

```bash
uvx second-brain-joplin@1.0.0 serve
uvx --python 3.13 --from "second-brain-joplin[semantic]==1.0.0" second-brain-joplin serve
```

or ask for the newest every time the server starts, with
`second-brain-joplin@latest` in place of `second-brain-joplin`. Naming the
version means you choose when a server that reads your notes changes.
[CHANGELOG.md](../CHANGELOG.md) says what each release changed.

## Other ways to install

**As an installed command, with uv:**

```bash
uv tool install second-brain-joplin
# with semantic search:
uv tool install --python 3.13 "second-brain-joplin[semantic]"
```

The command is then `second-brain-joplin serve` (no `uvx`), and
`uv tool upgrade second-brain-joplin` updates it. This is the form to use for
[HTTP mode](remote-access.md#keeping-it-running), where a service manager starts
the server.

**With pip,** into a virtual environment (Python 3.11 or newer):

```bash
python -m venv ~/.venvs/second-brain-joplin
~/.venvs/second-brain-joplin/bin/pip install second-brain-joplin
```

Give your client the full path to the command it installs,
`~/.venvs/second-brain-joplin/bin/second-brain-joplin` (on Windows,
`Scripts\second-brain-joplin.exe` inside the environment), with the argument
`serve`.

## If something doesn't work

See [troubleshooting.md](troubleshooting.md).
