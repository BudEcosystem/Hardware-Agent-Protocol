# Harness evidence snapshot

This directory contains selected source files copied from the user's existing local Bud Meta Harness checkout. It is not a download of a new repository and is not a claim to have read the whole repository. The source was inspected read-only at commit `655d7cec797c45f317ac623eca5319b50383b434`; `git status --short` was empty when captured.

`manifest.json` records capture time, source path, copied path, SHA-256, bytes, line count, and exact reading coverage. Nineteen files were read in full; three larger files were read only in the listed ranges. Search results from other files were used to locate seams and are not counted as full reads. No credentials or `.env` files were read or copied.

The resulting design is [harness-integration.md](../../docs/harness-integration.md). The most important findings are:

1. Existing native tools, deferred search, PTC, MCP, jobs, streams and durable delivery support the integration without an agent-loop rewrite.
2. Physical operation identity must survive a missing or canceled tool result. Runtime durability and idempotency need their own implementation.
3. Process-local job settlement, generic MCP timeout and stream closure do not establish that physical effects stopped.
4. The native typed source is more precise than some cookbook examples. In particular, JobSpec.owner is a SessionId, and MCP registration conflict rollback is to no tools, not always the previous generation.

The full end-to-end implementation, current behavior tests, performance measurements and device validation remain outstanding.
