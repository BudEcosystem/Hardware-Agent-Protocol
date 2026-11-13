# Local MCP integration

The original Python MCP projection exposes fourteen checked `hardware_*` tools,
including five procedure tools. The retained native Harness overlay still exposes
its nine primitive tools; extending that overlay requires a new integration run.
The projection connects to the existing HMS daemon through the private Linux
Unix socket and implements stdio protocol versions **2026-07-28** and
**2025-11-25**. It has no HTTP listener, automatic daemon initialization, physical
adapter or production MCP SDK dependency.

Start the daemon using the [local walkthrough](local-control.md), then configure a local MCP client to launch:

```sh
python3 -m hms.mcp --socket /absolute/private/directory/control.sock
```

Set the process working directory to the HMS source root and use the Python environment containing its existing `jsonschema` dependency. Standard output contains only newline-delimited JSON-RPC. Configure this server only in a trusted local execution world: every process under its Unix UID shares the daemon's authority. MCP `clientInfo`, request IDs, progress tokens and conversation metadata cannot impersonate another HMS principal.

## Tools and lifecycle

The tools are `hardware_discover`, `hardware_describe`, `hardware_observe`, `hardware_namespace`, `hardware_prepare`, `hardware_invoke`, `hardware_operation`, `hardware_events` and `hardware_cancel`. Their input and output schemas come from the [local API](../schemas/local-api.schema.json), with only reachable local definitions. No schema reference is fetched over the network. Host byte, numeric, exact-integer and semantic checks remain stronger than shape validation alone.

The additional tools are `hardware_procedure_submit`, `hardware_procedure_status`,
`hardware_procedure_cancel`, `hardware_procedure_resume` and
`hardware_procedure_events`. They use the same checked API projection. See
[bounded procedures](bounded-procedures.md) for the exact identity, restart and
cancellation contract. A parent stop acknowledgement can report denied delivery
to its active child; inspect unresolved child operation state separately.

For 2026-07-28, every request includes `_meta['io.modelcontextprotocol/protocolVersion']` and `_meta['io.modelcontextprotocol/clientCapabilities']`. `server/discover` is available but not required before tools. Results carry `resultType: complete` and server identity metadata. For 2025-11-25, call `initialize`, then send `notifications/initialized`; legacy `ping` is supported. A modern request remains independently validated even after legacy initialization. A request without modern fields follows legacy semantics only after that explicit handshake. Other protocol versions are not advertised.

The catalog has deterministic order, three tools per page, stable content-derived opaque cursors, and private 60-second cache hints for modern clients. Do not infer data freshness, authority or installed-device availability from that catalog cache. There are no task, prompt, resource, logging, sampling, elicitation or UI extensions. Modern subscriptions acknowledge an empty supported filter and remain bounded until client cancellation or transport closure; they do not stream operation events. Use `hardware_events` with its durable operation cursor.

Successful tool results contain `structuredContent: {"ok":true,"result":...}`. Tool failures contain `{"ok":false,"error":{"code":...,"outcome":"unconfirmed"}}` and set `isError: true`. Each result also includes an identical serialized JSON text block. Unknown tools and malformed MCP method envelopes use JSON-RPC errors. Unknown exceptions expose no stack, path or secret in tool content.

## Cancellation, delivery and recovery

Retain the entire prepared request before invocation. MCP request IDs are delivery correlation; HMS replay namespaces, operation keys and operation IDs are separate durable identities. Preparation does not admit work. Simulation completion remains physically unverified.

A `notifications/cancelled` message abandons that MCP result; it does not invoke `hardware_cancel`. The adapter suppresses a canceled reply that has not yet been committed to its output queue. A committed response can win the delivery race. An already dispatched checked-client call is allowed to finish within its transport limits, with its worker slot retained; the result is discarded if canceled. No replacement operation is submitted. Only the explicit domain cancellation tool asks HMS to cancel, and its acknowledgement still does not prove physical rest.

EOF, a killed MCP process, malformed/lost replies or output backpressure likewise do not roll back an accepted operation. Inspect its retained operation ID. If the invocation reply was lost, a deliberate exact replay of the retained request can resolve it while the original replay namespace is valid. Never generate a new operation key, refresh generations or rebuild the intent merely to obtain a successful response. Expired authority or missing retained state requires reconciliation.

## Bounds and evidence

The profile accepts at most 65,536 UTF-8 bytes per input line, with the host JSON depth/node/numeric restrictions. JSON-RPC IDs are strings of at most 128 characters or exact safe integers. Duplicate object fields, non-JSON numbers, invalid Unicode and JSON batches are rejected. An oversized or stalled partial frame terminates the transport. An in-flight request-ID collision also terminates it, since two results cannot be correlated safely.

There are at most eight tool workers and eight empty subscriptions. Tool admission uses a per-process token bucket of 16 calls, replenished at eight per second. Canceled workers retain capacity until they finish. Rate/concurrency refusal happens before local dispatch and uses application protocol codes 1002/1001. This is local load control, not a physical command-rate guarantee or a defense against another process of the same Unix UID.

Each output is limited to 524,288 bytes; the queue holds at most 32 messages and 2,097,152 bytes. Partial input and queued output have separate two-second whole-frame deadlines. Output exhaustion or a pipe failure closes the connection and leaves possible effects unconfirmed. Idle connections may remain open. The event loop uses nonblocking Linux pipes/stream sockets, not regular files. Daemon worker threads permit prompt process shutdown even if local filesystem work stalls; no hard CPU, filesystem or physical deadline is claimed.

The [modern protocol tests](../tests/test_mcp.py) exercise actual stdio preparation, invocation, schema-checked reads, exact replay and errors through a real local daemon. A deterministic checked-client reply gate demonstrates cancellation after actual admission: the operation completes, domain cancellation remains unrequested, the MCP reply is suppressed, and exact replay preserves one effect. That gate test controls the Projection boundary rather than reproducing a real external network outage.

The independent [SDK tester](../scripts/check_mcp_sdk.py) uses installed Python MCP SDK 1.26.0 only as a **legacy 2025-11-25 client**, with a real daemon and subprocess. Its [retained SDK receipt](../artifacts/verification/mcp-sdk-compact-host.json) records three simulated scenarios, advertised-schema checks, restart replay and explicit future-operation cancellation. It is not a current-version SDK test, a physical device test, or universal client certification. The SDK's timeout behavior does not itself prove a cancellation notification was sent.

The [independent review](../artifacts/verification/mcp-independent-review.json) retains nine additional regressions covering malformed metadata, worker limits, duplicate IDs, partial frames and unread output. A real-pipe EOF test uses a controlled checked-client reply gate after actual daemon admission; it confirms that transport closure leaves the simulated operation uncanceled and replay preserves one effect. Review also fixed exact-integer input validation before client canonicalization. That historical integration used the 289-test source snapshot. The current full-suite [receipt](../artifacts/verification/local-runtime.json) and [progress record](../PROGRESS.md) identify the exact current evidence; later sources are not validated by an older receipt.

The [source review](../research/mcp/README.md) distinguishes complete bounded pages, selected TypeScript/legacy transport coverage, and the generated schema's validation use. HTTP authorization, remote/per-agent principals, durable task extensions, real observation streams and broader client compatibility remain separate work.

The retained SDK rerun on the pre-installed-support snapshot validates 39 replies across the three SQLite-simulator scenarios with the updated output enums. The [earlier SDK receipt](../artifacts/verification/mcp-sdk.json) remains historical. That older rerun uses the SQLite simulator. The separate pre-installed-support [compact MCP receipt](../artifacts/verification/compact-mcp/verification.json) now covers actual modern and legacy client calls through the daemon to the C endpoint: six scenario executions, 81 validated replies, exact replay and native frame correlation. A modern host-SIGKILL case recovers by QUERY while retaining endpoint lifetime; MCP process close leaves future host work admitted until explicit HMS cancel. Both compact MCP tests also pass against the current installed-support implementation in the 289-test full suite; the detailed 81-reply captures remain pinned to their earlier source snapshot. This remains synthetic, same-UID evidence, with no independent physical stop claim.
