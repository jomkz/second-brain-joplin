# Security Policy

## Reporting a vulnerability

Please report suspected vulnerabilities privately via GitHub Security Advisories
(**Security → Report a vulnerability** on the repository) rather than opening a
public issue. We aim to acknowledge reports within a few days.

## Data handling & privacy

`second-brain-joplin` is designed to keep your notes local:

- **Local-only API.** The server talks to Joplin's Web Clipper REST API on
  `localhost` (default `http://localhost:41184`). It does not send your notes to
  any third-party service.
- **Runs on your machine.** The MCP server runs locally, launched by your MCP
  client (e.g. Claude Code). Your Joplin API token is read from the environment
  (`JOPLIN_API_TOKEN`) and is never committed — keep it out of version control.
- **Least privilege.** Anything an MCP client can read, the connected AI can
  read. Don't expose notebooks containing credentials, regulated data, or other
  people's private information. Apply least privilege to your notes.
- **No silent writes.** v0.1 tools are read-oriented and stubbed. Note creation
  is planned as an explicit **human-gated** flow in v0.4 — no writes happen
  without your confirmation.

See also the privacy considerations in
[docs/reference/second-brain-inspiration.md](docs/reference/second-brain-inspiration.md).
