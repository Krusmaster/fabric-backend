# server.json schema (test fixture)

`server.schema.json` is the MCP Registry's schema for `server.json`, version 2025-12-11, copied unmodified on
12 November 2026 from `https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json` (the `$schema`
URL the repository's `server.json` names). `tests/test_r1_mcp_registry.py` validates `server.json` against it without
a network call.

Source repository: github.com/modelcontextprotocol/registry (`docs/reference/server-json/`). Licence: that
repository's `LICENSE` (the MCP project is moving from MIT to Apache-2.0; contributions not yet relicensed remain MIT).

When the registry publishes a newer schema version and `server.json` moves to it, replace the file and the date here.
