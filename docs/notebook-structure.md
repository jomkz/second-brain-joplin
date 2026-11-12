# Notebook structure

The [PARA method](https://fortelabs.com/blog/para/) maps cleanly onto Joplin
notebooks and works well when an AI assistant is reading and filing your notes.
This is a recommended starting layout, not a requirement — the MCP tools work
with any structure.

| Notebook | Holds | Capture habit |
|----------|-------|---------------|
| **Inbox** | Anything unsorted: ideas, links, "look this up later" | Everything lands here first; no organizing at capture time |
| **Projects** | Things with a goal and an end date | One note (or sub-notebook) per project |
| **Areas** | Ongoing responsibilities with no end date (health, finances, courses) | One note per area; append over time |
| **Resources** | Reference material you might need someday | Topic per note |
| **Archive** | Completed projects and inactive areas | Move here instead of deleting |

## Why it suits an AI second brain

- **Frictionless capture** into a single Inbox means you actually record things;
  the assistant can help sort them during a weekly review.
- **Stable top-level notebooks** give the AI predictable places to search and
  file notes (e.g. "add this to my Inbox", "what's still unsorted?"). Setting
  `SBJ_WRITE_NOTEBOOKS=Inbox` lets it add notes to the Inbox and nowhere else
  ([Creating notes](remote-access.md#creating-notes)).
- **Append-only logs** in Areas ("what did I log at the gym this week?") turn
  your own notes into something you can ask questions of.

See [reference/second-brain-inspiration.md](reference/second-brain-inspiration.md)
for the article that inspired this layout.

## Templates

[templates/](../templates/README.md) has starter notes to import into Joplin: a
project, an area, a resource and a weekly review. They are plain Markdown, work
with or without Joplin's Templates plugin, and your assistant can fill one in
and file it in your Inbox.
