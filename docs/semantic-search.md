# Semantic search

Semantic search finds notes by *meaning* rather than exact keywords. It embeds
your notes with a local model, stores the vectors in a persistent on-disk index,
and answers queries with the nearest notes plus a similarity score. It
complements — it does not replace — the keyword `joplin_search`.

## Tools

| Tool | What it does |
|---|---|
| `joplin_semantic_search(query, limit=10)` | Returns the `limit` most similar notes (`id`, `title`, `excerpt`, `score`). Runs a quick incremental sync first (unless disabled). |
| `joplin_reindex(full=False)` | Syncs the index. `full=True` drops and re-embeds everything; otherwise only notes changed since the last sync are re-embedded. |

Build the initial index once after enabling the feature (this downloads the
embedding model the first time). From the command line, with no time limit:

```bash
uvx --from "second-brain-joplin[semantic]" second-brain-joplin reindex        # incremental
uvx --from "second-brain-joplin[semantic]" second-brain-joplin reindex --full # from scratch
```

or call `joplin_reindex` from your MCP client. Subsequent searches keep the index
fresh automatically. In HTTP mode the server also syncs it in the background every
`SBJ_SYNC_INTERVAL_MINUTES` (default 15, 0 = off), and `joplin_reindex(full=True)`
is refused there, because a full rebuild can outlast a remote tool call; use the
command above on the server's machine (see [remote-access.md](remote-access.md)).

## Installation

Semantic search is an optional extra so the base install stays light:

```bash
uvx --from "second-brain-joplin[semantic]" second-brain-joplin serve
```

The default stack is **FastEmbed** (ONNX, no PyTorch) + **`sqlite-vec`** (a
single-file index). To use other backends, install the matching extra and set
the env var:

| Goal | Install | Env |
|---|---|---|
| Default (light) | `[semantic]` | — |
| bge-m3 quality | `[semantic,semantic-st]` | `SBJ_EMBEDDING_BACKEND=sentence-transformers` |
| ChromaDB store | `[semantic,semantic-chroma]` | `SBJ_VECTOR_STORE=chroma` |

## Configuration (`SBJ_*`)

| Variable | Default | Notes |
|---|---|---|
| `SBJ_EMBEDDING_BACKEND` | `fastembed` | or `sentence-transformers` |
| `SBJ_EMBEDDING_MODEL` | backend default | `bge-small-en-v1.5` (FastEmbed) / `bge-m3` (ST) |
| `SBJ_VECTOR_STORE` | `sqlite-vec` | or `chroma` |
| `SBJ_INDEX_DIR` | `$XDG_DATA_HOME/second-brain-joplin/index` | falls back to `~/.local/share/...` |
| `SBJ_SEMANTIC_AUTO_SYNC` | `true` | re-sync before each search |

Changing the embedding model (or its dimensionality) is detected automatically:
the next sync rebuilds the index from scratch.

## How it works

- **Chunking.** Each note is split into overlapping ~1000-character chunks,
  prefixed with the note title, and embedded per chunk. Search results are
  deduplicated to one hit per note (the best-scoring chunk).
- **Incremental sync.** Each note's Joplin `updated_time` is stored as a version
  marker. A sync lists every note's id + `updated_time` (cheap, no bodies),
  re-embeds only the ones that changed, and drops notes deleted in Joplin.
- **Persistence.** The index lives at `SBJ_INDEX_DIR` and survives restarts.
- **Notebook filter.** With `SBJ_NOTEBOOKS` or `SBJ_EXCLUDE_NOTEBOOKS` set
  ([remote-access.md](remote-access.md#choosing-which-notebooks-are-exposed)),
  only visible notes are indexed, and a note that becomes hidden is dropped at
  the next sync, before anything new is embedded. Every search also asks Joplin
  which notes are visible now and returns only those, even when
  `SBJ_SEMANTIC_AUTO_SYNC` is off. The index file is shared by every process
  with the same `SBJ_INDEX_DIR`, so run `second-brain-joplin reindex` with the
  same settings as the server (`--env-file`); the command says whether a filter
  was set.
- **A failed sync leaves the index alone.** A sync asks Joplin for its notes
  before it touches the index, so a rebuild started while Joplin is down doesn't
  empty it.

## Privacy

The index is stored **unencrypted** on disk and contains note text excerpts and
titles in addition to the embedding vectors — treat it as sensitive as your
notes. The embedding model is downloaded once over the network and cached; your
note content is embedded locally and never leaves your machine. See
[SECURITY.md](../SECURITY.md).
