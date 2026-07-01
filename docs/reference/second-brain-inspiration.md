# Inspiration & references

This project draws on prior art for the "second brain + AI assistant" pattern.
We link and summarize rather than reproduce third-party content.

## Source article

**"How I Built My Second Brain with Obsidian and Claude (MCP Included)"** —
Syed Ali Turab, Medium (Jun 2026).
<https://medium.com/@syedturab97/how-i-built-my-second-brain-with-obsidian-and-claude-mcp-included-66bf656a3179>

### Takeaways we build on

- **Plain-text, user-owned notes.** Your knowledge base should be yours (in
  Joplin's case, a local store reachable via the Web Clipper REST API), not a
  proprietary silo. If the app disappears, your notes remain.
- **PARA-style structure.** A simple, durable layout — Inbox, Projects, Areas,
  Resources (plus Archive) — keeps capture frictionless and retrieval sane. See
  [notebook-structure.md](../notebook-structure.md).
- **MCP turns a filing cabinet into an assistant.** Exposing read/search/create
  over MCP lets an AI client work *inside* your notes (find, summarize, file)
  instead of you pasting snippets. This is exactly what `second-brain-joplin`
  provides for Joplin.
- **Least privilege for your notes.** Think before pointing an AI at a store;
  keep anything sensitive out of what you expose. This informs our
  [security & privacy](../../SECURITY.md) stance and the human-gated write flow
  planned for v0.4.

## Related project

- [second-brain-mcp](https://github.com/noesskeetit/second-brain-mcp) — the same
  use case for Obsidian (plain `.md` files on disk). `second-brain-joplin` covers
  Joplin via its REST API.
