# Configuration

Everything is set with environment variables: two for reaching Joplin
(`JOPLIN_*`) and the rest for the server itself (`SBJ_*`). The only one you must
set is `JOPLIN_API_TOKEN`. This page lists all of them, says where the server
reads them from, and describes the command line.

- [Where settings come from](#where-settings-come-from)
- [Joplin](#joplin) · [Notebooks](#notebooks) · [Semantic search](#semantic-search) ·
  [HTTP mode](#http-mode) · [Sign-in](#sign-in)
- [Command line](#command-line)
- [Optional installs](#optional-installs)

## Where settings come from

For each setting the server takes the first of these that gives a value:

1. **A `serve` option** on the command line, for the settings that have one
   (`--transport`, `--host`, `--port`, `--path`, `--public-url`).
2. **The environment** the server was started with. For a local client this is
   the `env` block of the client's MCP configuration
   ([install.md](install.md)).
3. **The file named by `--env-file`**: plain `KEY=value` lines. Use it for a
   server that a service manager starts, and keep it readable by you only
   (`chmod 600`), since it holds the Joplin token.
4. **A `.env` file,** in a development checkout only (see below).
5. **The default.**

Things to know:

- **Settings are read when the server starts.** Restart it after a change. In
  Claude Code, `/mcp` reconnects a server.
- **A variable set to nothing doesn't count as set** in step 2, so an empty
  `SBJ_NOTEBOOKS=` exported by a shell can't cancel the filter written in your
  env file. If a filter variable is still empty after every source is read, the
  server refuses to start: "show nothing" and "no filter" are opposite readings
  of it.
- **Remove a variable rather than leave it empty.** Most settings fall back to
  their default when empty, but four don't: an empty `JOPLIN_BASE_URL`,
  `SBJ_EMBEDDING_BACKEND` or `SBJ_VECTOR_STORE` is used as it is and fails, and
  an empty `SBJ_SEMANTIC_AUTO_SYNC` means false.
- **Lists are comma-separated,** and spaces around an entry are ignored. A
  notebook whose title contains a comma has to be named by its id.
- **True or false:** `1`, `true`, `yes` and `on` mean true, in any letter case.
  Anything else means false.
- **`.env` is for development.** Running from a clone of this repository, the
  server reads the `.env` at the top of that clone
  ([CONTRIBUTING.md](../CONTRIBUTING.md#running-the-server-locally)). An
  installed server reads no `.env` at all: not one in the directory it is
  started in, which is whatever project your MCP client has open, and not one in
  a directory above where it is installed, such as `~/.env`. A `.env` can point
  the server at a different Joplin or switch note creation on, so the only
  settings file an installed server reads is the one you name with `--env-file`.
  (Until 1.0.1 an installed server also read a `.env` from any directory above
  its install location.)
- **FastMCP's own settings.** FastMCP, the library this server is built on, has
  `FASTMCP_*` settings of its own, such as its log level. The server lets it
  read those from the environment, never from a `.env` in the working directory,
  and always chooses the transport itself: `FASTMCP_TRANSPORT` has no effect.
  Use `--transport` or `SBJ_TRANSPORT`.

## Joplin

| Variable | Default | |
|---|---|---|
| `JOPLIN_API_TOKEN` | none | **Required.** The token from Joplin Desktop: **Tools → Options → Web Clipper** (on macOS, **Joplin → Settings → Web Clipper**). Without it the server still starts, and a tool that asks Joplin for anything answers that Joplin rejected the request |
| `JOPLIN_BASE_URL` | `http://localhost:41184` | Where Joplin's Web Clipper service listens. Change it only if you changed the port in Joplin |

The server gives Joplin ten seconds to answer each request. Joplin's API takes
the token in the address of each request, which is why Joplin should only ever
be reached on the same machine, and why HTTP mode keeps that address out of its
logs.

## Notebooks

These apply to every tool, over stdio and HTTP alike.

| Variable | Default | |
|---|---|---|
| `SBJ_NOTEBOOKS` | none: every notebook | Only these notebooks are visible |
| `SBJ_EXCLUDE_NOTEBOOKS` | none | These notebooks are hidden |
| `SBJ_WRITE_NOTEBOOKS` | none: read-only | New notes may be created in these notebooks. `*` means every visible notebook. Without it `joplin_create_note` doesn't exist |

- An entry is a notebook's **id or its exact title**, and covers that notebook
  and every notebook under it. Prefer ids: an id survives a rename, and a title
  must belong to one notebook only.
- **Hiding wins.** With both filter variables set, a notebook is visible when
  the first covers it and the second doesn't. A hidden notebook can't be
  written to, whatever `SBJ_WRITE_NOTEBOOKS` lists.
- **A setting that doesn't match Joplin's notebooks is refused,** never read as
  "everything". The server won't start (when Joplin isn't answering at start-up
  it starts, and checks on every call instead). If a notebook is renamed or
  deleted while it runs, a wrong filter makes every tool refuse, and a wrong
  `SBJ_WRITE_NOTEBOOKS` makes `joplin_create_note` refuse, until the setting is
  fixed.
- `second-brain-joplin notebooks` lists every notebook with its id and shows
  what your settings make of it ([below](#second-brain-joplin-notebooks)).

The rules in full:
[Choosing which notebooks are exposed](remote-access.md#choosing-which-notebooks-are-exposed)
and [Creating notes](remote-access.md#creating-notes).

## Semantic search

These matter only with the `[semantic]` install
([semantic-search.md](semantic-search.md)).

| Variable | Default | |
|---|---|---|
| `SBJ_EMBEDDING_BACKEND` | `fastembed` | `fastembed`, or `sentence-transformers` (needs the `[semantic-st]` install too) |
| `SBJ_EMBEDDING_MODEL` | the backend's default | A model id. The defaults are `BAAI/bge-small-en-v1.5` for FastEmbed and `BAAI/bge-m3` for sentence-transformers |
| `SBJ_VECTOR_STORE` | `sqlite-vec` | `sqlite-vec`, or `chroma` (needs the `[semantic-chroma]` install too) |
| `SBJ_INDEX_DIR` | `~/.local/share/second-brain-joplin/index` | Where the index is kept. With `XDG_DATA_HOME` set, the default is `$XDG_DATA_HOME/second-brain-joplin/index`. On Windows `~` is your user folder, so the default is `C:\Users\<you>\.local\share\second-brain-joplin\index` |
| `SBJ_SEMANTIC_AUTO_SYNC` | `true` | Bring the index up to date before each semantic search. With `false`, a search doesn't sync first: the index changes when you call `joplin_reindex` or run the `reindex` command, and in HTTP mode also at each background sync (`SBJ_SYNC_INTERVAL_MINUTES`) |

- **Changing the model rebuilds the index** at the next sync, without being
  asked.
- **The index holds text from your notes,** unencrypted. Treat the directory as
  you treat the notes ([SECURITY.md](../SECURITY.md#semantic-search)).
- **Every server and command that shares an index directory shares the index.**
  Run `second-brain-joplin reindex` with the same settings as the server
  (`--env-file`), or it indexes notes the server's filter hides.

## HTTP mode

These matter only for `serve --transport http`
([remote-access.md](remote-access.md)).

| Variable | Option | Default | |
|---|---|---|---|
| `SBJ_TRANSPORT` | `--transport` | `stdio` | `stdio` for a client on the same machine, `http` for a Claude custom connector |
| `SBJ_HOST` | `--host` | `127.0.0.1` | The address to listen on. Keep it on loopback and let a tunnel or reverse proxy publish it |
| `SBJ_PORT` | `--port` | `8775` | 1 to 65535 |
| `SBJ_HTTP_PATH` | `--path` | `/mcp` | The path of the MCP endpoint; it must start with `/` |
| `SBJ_PUBLIC_URL` | `--public-url` | none | The server's public origin, such as `https://joplin.example.com`: `https`, no path. Sign-in requires it |
| `SBJ_RATE_LIMIT_PER_MINUTE` | | `60` | Tool calls per minute for each signed-in account, with bursts of half that. `0` turns the limit off |
| `SBJ_SYNC_INTERVAL_MINUTES` | | `15` | Minutes between background syncs of the semantic index. `0` turns them off |

There is no variable for `--no-auth`. Running without sign-in has to be visible
on the command line, and is accepted only on a loopback address with no public
URL ([Start-up refusals](remote-access.md#start-up-refusals)). A setting the
server can't use (a port that isn't a number, a public URL with a path, sign-in
half configured) stops it from starting, with a message that names the setting;
[troubleshooting.md](troubleshooting.md#http-mode) lists them.

## Sign-in

HTTP mode signs you in with GitHub and lets in only the accounts you list. Set
the first four together or not at all
([Sign-in](remote-access.md#sign-in)).

| Variable | Default | |
|---|---|---|
| `SBJ_GITHUB_CLIENT_ID` | none | The client id of your GitHub OAuth App |
| `SBJ_GITHUB_CLIENT_SECRET` | none | Its client secret |
| `SBJ_JWT_SIGNING_KEY` | none | At least 32 characters, for example from `openssl rand -base64 32`. Changing it signs every client out |
| `SBJ_ALLOWED_GITHUB_IDS` | none | The numeric GitHub user ids allowed in, separated by commas or spaces. Ids, not logins: `https://api.github.com/users/<login>` shows yours |
| `SBJ_OAUTH_REDIRECT_URIS` | `https://claude.ai/api/mcp/auth_callback` | The OAuth clients allowed to register, as `https` addresses separated by commas or spaces. The default admits claude.ai only |

## Command line

```
second-brain-joplin [--version] <command> [options]
```

Run with no command it prints its help. It exits with `0` on success, `2` when
it refuses a configuration (the message says what to fix), and `1` when Joplin
or the semantic install is the problem.

### `second-brain-joplin serve`

Starts the MCP server. This is the command an MCP client runs.

| Option | |
|---|---|
| `--transport {stdio,http}` | `stdio` (default) or `http` |
| `--host`, `--port`, `--path`, `--public-url` | HTTP mode: see the table [above](#http-mode). Given with stdio, they are refused |
| `--no-auth` | HTTP mode without sign-in, on loopback only, for a local test |
| `--env-file PATH` | Read settings from this file first. A missing file is an error |

### `second-brain-joplin reindex`

Builds or updates the semantic index from the command line, with no time limit.
Use it for the first build and for a full rebuild. It needs the `[semantic]`
install and Joplin running.

| Option | |
|---|---|
| `--full` | Throw the index away and embed every note again |
| `--env-file PATH` | Read settings from this file first |

It prints what changed, and whether a notebook filter was in force:

```
added=158 updated=0 deleted=0 total=158 model=BAAI/bge-small-en-v1.5
Notebook filter: not set; every note is indexed. If the server has one, run this with the server's --env-file.
```

### `second-brain-joplin notebooks`

Lists every notebook with its id and note count, marked `hidden`, `visible` or
`writable` under the settings it was run with. Use it to find the ids for the
notebook settings, and to check them before a client sees through them. It needs
Joplin running.

| Option | |
|---|---|
| `--env-file PATH` | Read settings from this file first |

```
Notebook filter: 3 of 4 notebooks visible.
Note creation: allowed in the 1 marked writable.
writable  c7d1e5a09b3f4c2d8e6f1a0b9c8d7e6f  Inbox (4)
hidden    5a1f0c2e9b7d4f63a8e1c0d2b4f6a7c9  Journal (212)
visible   9c40d1e7a3b24f58b6c9e0f1a2d3b4c5  Work (57)
visible   0b7e3f9a1c2d4e5f8a7b6c5d4e3f2a1b    Projects (31)
```

It lists hidden notebooks too, because this is your own terminal. When the
settings don't match Joplin's notebooks, it still prints the tree, with `?` for
each mark, and then says which entry is wrong.

## Optional installs

The base install has the read tools and note creation. Semantic search comes as
optional extras, so that the base stays small:

| Extra | Adds | For |
|---|---|---|
| `semantic` | FastEmbed and sqlite-vec | Semantic search with the default stack |
| `semantic-st` | sentence-transformers | The `bge-m3` model; install together with `semantic` and set `SBJ_EMBEDDING_BACKEND=sentence-transformers` |
| `semantic-chroma` | ChromaDB | A Chroma index; install together with `semantic` and set `SBJ_VECTOR_STORE=chroma` |

With `uvx`, name the extra in `--from`:

```bash
uvx --python 3.13 --from "second-brain-joplin[semantic]" second-brain-joplin serve
```

`--python 3.13` is there on purpose: see
[Which Python](install.md#which-python).
