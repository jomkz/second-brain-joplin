# Installation

> This document is a stub. Full setup guide is tracked in GitHub issue T6.

## Prerequisites

- Joplin Desktop installed and running
- Web Clipper service enabled: **Tools → Options → Web Clipper → Enable Web Clipper Service**
- API token copied from that same settings panel
- Python ≥ 3.11 or `uvx` (recommended)

## Claude Code

```bash
claude mcp add -s user second-brain-joplin \
  -e JOPLIN_API_TOKEN=your-token-here \
  -- uvx second-brain-joplin serve
```

## Cursor / other MCP clients

See client documentation for MCP server configuration. Use:

- **Command**: `uvx second-brain-joplin serve`
- **Env**: `JOPLIN_API_TOKEN=your-token-here`
- **Env**: `JOPLIN_BASE_URL=http://localhost:41184` (default, change only if customized)
