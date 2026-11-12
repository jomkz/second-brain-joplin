# Tool reference

The server offers seven MCP tools. Six are always there and never change
Joplin. The seventh, `joplin_create_note`, exists only once you list the
notebooks that may receive notes ([`SBJ_WRITE_NOTEBOOKS`](configuration.md#notebooks)).

| Tool | What it does | Changes |
|---|---|---|
| [`joplin_overview`](#joplin_overview) | Lists the notebooks as a tree, with note counts | Nothing |
| [`joplin_search`](#joplin_search) | Finds notes by keyword | Nothing |
| [`joplin_read`](#joplin_read) | Reads one note, a page at a time | Nothing |
| [`joplin_recent`](#joplin_recent) | Lists the notes changed in the last N days | Nothing |
| [`joplin_semantic_search`](#joplin_semantic_search) | Finds notes by meaning | Nothing in Joplin (it may refresh the local index first) |
| [`joplin_reindex`](#joplin_reindex) | Builds or refreshes the semantic index | The local index only, never Joplin |
| [`joplin_create_note`](#joplin_create_note) | Adds one new note to a notebook you allow | A new note; it can't edit, move or delete |

What holds for every tool:

- **Arguments are checked first.** A value outside the range given below is
  refused before Joplin is asked anything.
- **Ids are Joplin's:** 32 hexadecimal characters, for notes and notebooks alike.
- **Times are ISO 8601 in UTC,** for example `2026-11-12T17:09:49.545000+00:00`.
- **Results are structured.** Each tool declares an output schema, and a result
  comes back both as JSON text and as MCP structured content. A tool that
  returns a list wraps it there as `{"result": [...]}`; the examples below show
  the list itself.
- **A notebook filter applies to all of them** when you set one: see
  [With a notebook filter](#with-a-notebook-filter).

The examples use made-up notes.

## `joplin_overview`

Lists the notebooks as a tree with the number of notes in each. It takes no
arguments. Use it to learn the notebooks' names and ids before a search, or
before creating a note.

Returns a list of top-level notebooks, each with:

| Field | Type | |
|---|---|---|
| `id` | string | The notebook's id |
| `name` | string | Its title |
| `note_count` | integer | Notes directly in it, not counting its sub-notebooks |
| `children` | list | Its sub-notebooks, in the same shape |

```json
[
  {
    "id": "c7d1e5a09b3f4c2d8e6f1a0b9c8d7e6f",
    "name": "Inbox",
    "note_count": 4,
    "children": []
  },
  {
    "id": "9c40d1e7a3b24f58b6c9e0f1a2d3b4c5",
    "name": "Work",
    "note_count": 57,
    "children": [
      {
        "id": "0b7e3f9a1c2d4e5f8a7b6c5d4e3f2a1b",
        "name": "Projects",
        "note_count": 31,
        "children": []
      }
    ]
  }
]
```

## `joplin_search`

Finds notes by keyword, using Joplin's own search. The query takes
[Joplin's search syntax](https://joplinapp.org/help/apps/search), so
`title:remodel`, `tag:todo` and `"exact phrase"` work as they do in the app.

| Argument | Type | Default | Allowed |
|---|---|---|---|
| `query` | string | required | Any Joplin search query |
| `limit` | integer | `10` | 1 to 50 |

Returns a list of hits, in Joplin's order:

| Field | Type | |
|---|---|---|
| `id` | string | The note's id, for `joplin_read` |
| `title` | string | The note's title |
| `excerpt` | string | The first 200 characters of the note on one line, ending in `…` when cut |

```json
[
  {
    "id": "4be0a1c2d3e4f5061728394a5b6c7d8e",
    "title": "Cabinet quotes",
    "excerpt": "Three quotes so far. - Northside: 8,400 - Hale & Sons: 9,150, installed"
  }
]
```

The excerpt is the start of the note, not the part that matched. To find a note
by what it means when you don't know its words, use
[`joplin_semantic_search`](#joplin_semantic_search).

## `joplin_read`

Reads one note's markdown. A long note comes a page at a time.

| Argument | Type | Default | Allowed |
|---|---|---|---|
| `note_id` | string | required | A note's id: 32 hexadecimal characters |
| `offset` | integer | `0` | 0 or more: the character to start from |
| `max_chars` | integer | `50000` | 1 to 100,000: the most characters to return |

Returns:

| Field | Type | |
|---|---|---|
| `id` | string | The note's id |
| `title` | string | Its title |
| `body` | string | Up to `max_chars` characters of markdown, starting at `offset` |
| `parent_id` | string | The id of the notebook it is in |
| `created_time` | string | When it was created |
| `updated_time` | string | When it was last changed |
| `offset` | integer | Where this page starts |
| `total_chars` | integer | The length of the whole note |
| `next_offset` | integer or null | Where the next page starts; null when this page reaches the end |

```json
{
  "id": "4be0a1c2d3e4f5061728394a5b6c7d8e",
  "title": "Cabinet quotes",
  "body": "Three quotes so far.\n\n- Northside: 8,400\n- Hale & Sons: 9,150, installed\n",
  "parent_id": "0b7e3f9a1c2d4e5f8a7b6c5d4e3f2a1b",
  "created_time": "2026-10-02T15:04:11+00:00",
  "updated_time": "2026-11-09T21:40:27.512000+00:00",
  "offset": 0,
  "total_chars": 73,
  "next_offset": null
}
```

To read a long note in full, call again with `offset` set to the last
`next_offset` until it comes back null. Claude limits how much one tool result
may hold, which is why a page stops at 100,000 characters.

A note that doesn't exist, and a note the notebook filter hides, get the same
answer: `The requested Joplin resource was not found.`

## `joplin_recent`

Lists the notes changed in the last N days, newest first. "Changed" is Joplin's
own updated time, so a new note counts too.

| Argument | Type | Default | Allowed |
|---|---|---|---|
| `days` | integer | `7` | 1 to 3650 |
| `limit` | integer | `20` | 1 to 100 |

Returns a list of:

| Field | Type | |
|---|---|---|
| `id` | string | The note's id |
| `title` | string | Its title |
| `updated_time` | string | When it was last changed |

```json
[
  {
    "id": "a03be000b6aa4b0fa66b9d2070974c55",
    "title": "Call the electrician",
    "updated_time": "2026-11-12T17:09:49.545000+00:00"
  }
]
```

## `joplin_semantic_search`

Finds notes by meaning: a question about "getting the kitchen done" can find a
note that only says "cabinet quotes". It needs the optional `[semantic]` install
and an index of your notes; see [semantic-search.md](semantic-search.md).

| Argument | Type | Default | Allowed |
|---|---|---|---|
| `query` | string | required | Plain language |
| `limit` | integer | `10` | 1 to 50 |

Returns a list of notes, closest first, one entry per note:

| Field | Type | |
|---|---|---|
| `id` | string | The note's id |
| `title` | string | Its title |
| `excerpt` | string | The first 200 characters of the part of the note that matched best. Each part starts with the note's title |
| `score` | number | Closeness, above 0 and at most 1; higher is closer |
| `chunk_index` | integer | Which part of the note that was, counting from 0 |

```json
[
  {
    "id": "4be0a1c2d3e4f5061728394a5b6c7d8e",
    "title": "Cabinet quotes",
    "excerpt": "Cabinet quotes Three quotes so far. - Northside: 8,400 - Hale & Sons: 9,150, installed",
    "score": 0.62,
    "chunk_index": 0
  }
]
```

- Before it searches, it brings the index up to date with the notes that
  changed, unless you turn that off
  ([`SBJ_SEMANTIC_AUTO_SYNC`](configuration.md#semantic-search)). The first
  search after many edits is slower for that reason.
- Scores compare results within one search. They mean nothing across searches
  or across embedding models.
- At most two semantic searches run at a time; more wait their turn.
- Without the `[semantic]` install the tool is still listed, and answers with
  how to install it.

## `joplin_reindex`

Builds or refreshes the semantic index. It reads from Joplin and writes only the
index on the server's disk.

| Argument | Type | Default | |
|---|---|---|---|
| `full` | boolean | `false` | `false`: embed only the notes that changed since the last sync. `true`: throw the index away and embed every note again |

Returns:

| Field | Type | |
|---|---|---|
| `added` | integer | Notes that weren't in the index before. A note with no text has nothing to embed, so it is counted here at every sync |
| `updated` | integer | Notes embedded again because they changed |
| `deleted` | integer | Notes dropped from the index (deleted in Joplin, or hidden by the filter) |
| `total` | integer | The notes visible in Joplin when the sync ran |
| `model` | string | The embedding model in use |

```json
{ "added": 3, "updated": 1, "deleted": 0, "total": 158, "model": "BAAI/bge-small-en-v1.5" }
```

- The first build downloads the embedding model and embeds every note, which
  can take minutes. `second-brain-joplin reindex` on the command line does the
  same with no time limit.
- **Over HTTP, `full: true` is refused,** because a full rebuild can outlast a
  remote tool call. Run `second-brain-joplin reindex --full` on the server's
  machine instead ([Indexing](remote-access.md#indexing)).
- If Joplin isn't answering, the index is left as it was.

## `joplin_create_note`

Adds one new markdown note to a notebook. This is the only tool that writes to
Joplin, and adding a note is all it does: it can't change, move or delete a
note. It is registered only when
[`SBJ_WRITE_NOTEBOOKS`](configuration.md#notebooks) is set, so on a server
without it a client can't see or call it.

| Argument | Type | Allowed |
|---|---|---|
| `title` | string | 1 to 300 characters. Line breaks and runs of spaces become single spaces |
| `body` | string | Up to 100,000 characters of markdown |
| `notebook` | string | The notebook's exact title, or its id |

Returns:

| Field | Type | |
|---|---|---|
| `id` | string | The new note's id |
| `title` | string | Its title as saved |
| `notebook_id` | string | The id of the notebook it went into |
| `notebook` | string | That notebook's title |
| `created_time` | string or null | When Joplin created it. Null for a repeat (`already_created: true`), and when Joplin's answer was lost or didn't say |
| `already_created` | boolean | `true` when this exact request made the note a moment ago and nothing new was written |

```json
{
  "id": "a03be000b6aa4b0fa66b9d2070974c55",
  "title": "Call the electrician",
  "notebook_id": "c7d1e5a09b3f4c2d8e6f1a0b9c8d7e6f",
  "notebook": "Inbox",
  "created_time": "2026-11-12T17:09:49.545000+00:00",
  "already_created": false
}
```

- **You approve each note in your client.** The call carries the notebook by
  name, the title and the text, so the approval prompt shows what will be
  written. See [Who confirms each note](remote-access.md#who-confirms-each-note).
- **Only listed notebooks.** Any other notebook gets one answer, whether it is
  hidden, missing or just not listed:
  `A note can't be created in that notebook.`, followed by the notebooks that
  can receive notes. Name a notebook by its id when two writable notebooks share
  a title.
- **A repeat doesn't make a second note.** The same notebook, title and text
  sent again within ten minutes returns the note already made, with
  `already_created: true`.
- **When Joplin fails,** the answer tells three cases apart. A plain Joplin
  error means nothing was created. A normal result means the note exists, even
  if Joplin's own answer was lost on the way back. An error ending in "may or
  may not have been created" means it can't be known yet, and trying again in a
  moment is safe.

More in [Creating notes](remote-access.md#creating-notes).

## With a notebook filter

[`SBJ_NOTEBOOKS` and `SBJ_EXCLUDE_NOTEBOOKS`](configuration.md#notebooks) limit
which notebooks every tool can see:

| Tool | With a filter |
|---|---|
| `joplin_overview` | Lists visible notebooks only. A visible notebook under a hidden one moves to the top of the tree |
| `joplin_search`, `joplin_recent` | Leave hidden notes out, and keep reading until `limit` is filled |
| `joplin_read` | Answers for a hidden note exactly as for one that doesn't exist |
| `joplin_semantic_search` | Returns only notes that are visible at that moment |
| `joplin_reindex` | Indexes visible notes only, and drops notes that became hidden |
| `joplin_create_note` | Can't write to a hidden notebook, whatever `SBJ_WRITE_NOTEBOOKS` lists |

The full rules are in
[Choosing which notebooks are exposed](remote-access.md#choosing-which-notebooks-are-exposed).

## Errors

A tool that can't do what was asked returns an error with a sentence the
assistant can pass on. These are the ones the server writes itself;
[troubleshooting.md](troubleshooting.md) says what to do about each.

| The error says | It means |
|---|---|
| `Joplin is unreachable at <address> — is Joplin Desktop running with the Web Clipper service enabled?` | Nothing answered at Joplin's address |
| `Joplin didn't answer at <address> within 10 seconds — is Joplin Desktop running and responsive?` | Joplin didn't answer in time |
| `Joplin rejected the request — check that JOPLIN_API_TOKEN is set and matches the token in Joplin's Web Clipper settings.` | The token is missing or wrong |
| `The requested Joplin resource was not found.` | No note has that id, or the filter hides it |
| `Joplin returned an unexpected response (HTTP <status>).` | Joplin answered with an error of its own |
| `The server's notebook settings (…) don't match Joplin's notebooks, so this is refused until they are fixed. …` | A notebook named in `SBJ_NOTEBOOKS`, `SBJ_EXCLUDE_NOTEBOOKS` or `SBJ_WRITE_NOTEBOOKS` was renamed or deleted. The client isn't told which one |
| `Semantic search needs the optional '<package>' dependency. …` | The `[semantic]` install is missing |
| `Unknown SBJ_EMBEDDING_BACKEND …` / `Unknown SBJ_VECTOR_STORE …` | A semantic setting has a value the server doesn't know |
| `A full rebuild can take longer than a remote tool call may run. …` | `joplin_reindex` with `full: true` over HTTP |
| `A note can't be created in that notebook. Notebooks that can receive notes: …` | `joplin_create_note` was given a notebook that isn't on the list |
| `Note creation is off on this server: its operator hasn't listed any notebook that may receive notes (SBJ_WRITE_NOTEBOOKS).` | `SBJ_WRITE_NOTEBOOKS` is set, and no notebook it covers is visible |
| `A note needs a title.` | The title was only spaces |
| `… The note may or may not have been created: look in Joplin, or try again in a moment (a repeat of this request won't make a second copy).` | Joplin took the request and didn't answer |
| `Rate limit exceeded for client: <id>` | HTTP mode: a burst of more than half [`SBJ_RATE_LIMIT_PER_MINUTE`](configuration.md#http-mode), or more than that many calls a minute kept up. The call is refused before any tool runs |

An argument outside its range is refused with a validation message that names
the argument and the limit, for example
`limit … Input should be less than or equal to 100`.

## What the tools tell the client about themselves

Every tool carries MCP annotations, which a client can use to decide when to ask
you first:

| Tool | `readOnlyHint` | `destructiveHint` | `idempotentHint` | `openWorldHint` |
|---|---|---|---|---|
| The four read tools and `joplin_semantic_search` | `true` | | | `false` |
| `joplin_reindex` | `false` | `false` | `true` | `false` |
| `joplin_create_note` | `false` | `false` | `false` | `false` |

`joplin_create_note` also carries `"anthropic/requiresUserInteraction": true`
in its metadata. Claude Code reads that as: ask on every call, with no "don't
ask again". Other clients ignore it.
