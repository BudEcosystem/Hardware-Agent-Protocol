# MCP specification review

The official latest specification resolved to **2026-07-28** on 2026-11-06. This lane pins the official repository at `3c4d91b7e832d9b74338d56eed03403ccc662123`, including selected current and legacy specification pages, source-of-truth TypeScript, generated JSON schema, and the upstream licensing notice. [Official latest specification](https://modelcontextprotocol.io/specification/latest).

The [manifest](manifest.jsonl) records 22 acquisitions. The [reading receipt](reading-mcp-full.json) records 19 complete bounded pages/files, selected TypeScript sections and the legacy stdio section. The generated JSON schema was retained and used as a test validator; it is not claimed fully read. Inline Mermaid diagrams were read as source. Linked specifications, HTTP authorization, extensions, and whole-repository/SDK implementation reading are outside this receipt.

`python3 research/mcp/audit_mcp.py` verifies file hashes, exact LF coverage hashes, all retained files' Git blob identities, and reconstructed Git trees from retained recursive metadata. The commit/tree association comes from HTTPS GitHub metadata; signature verification is not claimed. [Audit result](audit.json).

The upstream [license notice](raw/LICENSE) describes its MIT/Apache-2.0 transition and separate non-specification documentation licensing. Retained files are unchanged research sources; the HMS implementation is original. No acquired repository implementation was run. The installed Python MCP SDK is a separate, explicitly selected interoperability test dependency, documented in the test receipt rather than treated as part of this specification read.

See [design critique](notes/review.md) and the [local adapter](../../docs/mcp-integration.md). These sources specify agent-tool transport, not physical stop, authority fencing, durable effect receipts, or device conformance.
