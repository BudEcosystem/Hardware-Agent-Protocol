# Host invocation and journal profile — experimental v0.1

Status: an independently designed, incompatible-until-stabilized host profile. [The schema](../schemas/invoke.schema.json), [parser](../hms/contracts.py) and [journal](../hms/journal.py) are executable components, now used by the [local simulation runtime](09-local-runtime.md). The WoT fixtures project this full invocation envelope; placeholder HTTPS forms remain unimplemented. This is not a full HMS runtime or official Anthropic MHS implementation.

## Invocation and immutable intent

The JSON envelope has exactly `protocol: "hms.invoke/0.1"`, `replayNamespace`, `operationKey`, and `intent`. Unknown envelope/intent/timing fields are rejected. The authenticated principal and deployment are supplied by the trusted embedding service, not by JSON. Credentials, delegation/lease proofs and transport request IDs stay outside the immutable intent. This library has no credential parser; its `Context` is an in-process input, not proof of authentication.

Intent contains physical instance, endpoint execution session, control generation, action, description SHA-256 digest, commissioned binding generation, calibration revision, typed argument object, timing and required effect. IDs are case-sensitive bounded ASCII identifiers. `calibrationRevision` is explicit even when a capability's commissioned profile defines a named not-applicable revision. Changing any of these fields changes intent. Units and frames belong in the action's validated arguments; omission cannot mean an implicit unit conversion. `arguments` accepts JSON structure at the generic layer; the required admission policy must enforce the pinned capability's complete schema, required semantics and physical constraints.

`requiredEffect` is either `capability_completion` or `physical_verified`. The first still requires the pinned capability's completion evidence; the second also requires physical verification in the same completion-evidence submission. An earlier running-state observation cannot be recycled as final verification. Simulation cannot supply physical verification. Authenticated controller evidence may attest a physical measurement only if the binding's evidence policy actually supports it; labeling a command echo `controller` is insufficient.

Timing fields use integer milliseconds: `notBeforeUnixMs`, `latestStartUnixMs`, `maxRunMs`, `latestCompletionUnixMs`. The interval must be ordered; a start at or beyond `latestStartUnixMs` is expired. Admission may precede not-before, but dispatch cannot. Relative durations are positive and capped at 2³²−1 ms in this profile. These field definitions do not establish clock accuracy. A production dispatcher needs a qualified clock mapping and conservative uncertainty bounds, plus native enforcement for hard deadlines. The prototype only checks its injected host clock at admission and dispatch; it does not enforce run/completion deadlines or supply a timing guarantee.

## Parsing and digest

Use RFC 8785 JCS, with this narrower host input profile:

- UTF-8 without a BOM, at most 65,536 wire bytes, depth at most 32 and at most 16,384 tree nodes (object keys count as nodes).
- No duplicate decoded object keys, lone Unicode surrogates, non-finite numbers, negative zero or implicit conversion of non-JSON types. Strings retain their exact Unicode sequence; no normalization occurs.
- Integral numbers must fit ±(2⁵³−1), including integral values written with a decimal point/exponent. Non-integral numbers use finite binary64. A decimal token must round-trip through the implementation's shortest binary64 decimal spelling without changing its decimal value; excess supplied precision and underflow are rejected. Number tokens are at most 128 characters.
- Exact decimals or larger integers use schema-defined strings. Their canonical spelling, units and permitted range are an action-profile responsibility. JSON strings are never silently converted before hashing.
- This wire parser is bounded by the input cap. The separate in-memory canonicalization helper materializes its result before checking output size; it is not a streaming encoder for arbitrary untrusted Python objects.

The digest is lowercase `sha256:` plus SHA-256 of:

```text
ASCII("HMS-INTENT-JCS-SHA256-v0.1") || 0x00 || UTF8(JCS(intent))
```

Only `intent` is hashed. The envelope's protocol selects these rules; unknown versions fail. A digest is identity/integrity data, not a signature or actuation authority. [Retained fixtures](../tests/fixtures/host-intents.json) pin exact bytes and digests. The implementation vendors unmodified Apache-2.0 `rfc8785.py` v0.1.4, with [provenance](../hms/_vendor/README.md). Full RFC/errata review and independent Python/Node comparisons are retained in [the host research lane](../research/host-contract/README.md) and [parser review](../artifacts/verification/host-contract-review.json).

## Replay namespace and result access

The runtime issues an opaque namespace containing its authority identity, monotonically increasing epoch and random token. The durable record binds it to authenticated principal and deployment and an immutable expiry. A client cannot mint one by formatting a string. The replay key is `(principal, deployment, namespace epoch/token, operationKey)`.

Existing-key lookup precedes new actuation admission. Result authorization precedes returning a result or reporting a changed-intent conflict. Identical intent returns the existing operation even if invoke permission or start time has since expired, provided result access remains authorized and the mapping remains retained. A different digest under that key is a conflict. A retained expired namespace may resolve existing mappings but cannot admit a new key.

Namespace expiries are nondecreasing within a principal/deployment series. Pruning advances the persisted minimum accepted epoch through a contiguous expired prefix in the same transaction that removes its key mappings. It never removes an unexpired mapping. Operation history and unresolved claims survive pruning; status by operation ID remains available under result authority. Old tokens cannot become new work after deletion or restart. A missing database is an error; explicit creation generates a new authority identity. Restoring a stale database/replay floor under an old live authority remains prohibited and is not solved by SQLite alone.

## Single-owner journal prototype

This first implementation requires a local POSIX file and one process holding an exclusive owner lock. Threads share a serialized connection. It uses SQLite `BEGIN IMMEDIATE`, foreign keys, rollback journal `DELETE` and `synchronous=EXTRA`, checked at startup. Admission, all resource claims/fence increments, replay mapping and first event commit together. An accepted operation is the durable pending-dispatch record. Claiming dispatch atomically records a unique attempt and owner epoch before returning a ticket. The ticket only records ownership; it cannot itself send or authorize a physical command.

The current environment uses SQLite 3.45.1. Current SQLite documentation describes a later fixed WAL-reset race; this prototype chooses rollback mode. `EXTRA` additionally synchronizes directory unlink commits in DELETE mode. The full source review and selected pragma coverage are recorded locally. Storage durability still depends on a correctly behaving filesystem/VFS/device; the tests kill processes, not power or storage controllers. No throughput or durability certification is claimed.

Opening an existing journal changes owner epoch and marks prior `dispatching`/`running` operations `outcome_unknown`; it retains claims and never resends. Accepted work remains pending and must pass a fresh dispatch check. Old worker tickets fail. Reconciliation requires explicit new evidence and preserves unknown history. Database fences alone do not fence an external endpoint or a surviving adapter process; those integration obligations remain mandatory.

Execution, cancellation and verification are separate projections. Canceling accepted work proves dispatch exclusion inside the single-owner transaction and can release claims. After dispatch, requesting or acknowledging cancellation cannot imply termination; a completion race can retain `completed` with cancellation acknowledged. Terminal evidence disputes append events without rewriting the terminal state. Terminal state alone does not release a resource: explicit trusted quiescence evidence is required after possible dispatch. Unknown outcomes retain their claims.

Trusted policies must implement authorization, complete admission, immediate pre-dispatch recheck and evidence validation. Callback snapshots are isolated from durable intent/projections. Policies must be bounded, nonblocking and must not reenter the journal. The test policy is synthetic and does not commission anything. Worker/evidence methods are internal trusted APIs; exposing them directly to models would bypass the intended boundary.

Fresh admission, namespace issuance/pruning and dispatch fail on detected clock rollback. A fresh time reading is durably checkpointed before business writes; transaction refusal also preserves any later observed floor in a separate metadata transaction. Otherwise an expired refusal or late duplicate receipt could roll back the clock floor and revive an old request. Failure to persist that floor poisons subsequent in-process mutations. Status/replay reads, cancellation and evidence recording remain possible when only the clock is degraded. Regressed/unavailable event clock readings are clamped to the persisted audit floor and explicitly marked from the same clock sample; event sequence provides ordering. These are host record times, not acquisition times or proof of when an effect occurred.

## Implemented boundary and next integration

Present: strict invocation parsing, versioned digest, durable replay windows, all-or-none resource claims, persisted dispatch ownership, lifecycle/evidence records, cancellation races, bounded event pages and conservative recovery. Tests include 24 concurrent duplicates and four abruptly terminated subprocess phases: accepted, dispatch claimed, synthetic effect persisted before receipt, and completed. Six further subprocess tests interrupt transactions for submit, dispatch, completion, cancellation, resource release and namespace pruning. Each forces dirty-page spill and confirms a nonzero rollback-journal header before interruption, then checks recovered integrity, exact event history, claims, replay mappings and fences.

The local simulation profile adds a versioned registry, policy admission, synthetic observation streams, a supervised scheduler, simulated endpoint fences, deadline checks and a CLI over Linux UID-authenticated Unix sockets. Its primitive state change and receipt share a simulator transaction; that property does not apply to physical hardware. Preparation, immutable request identity and current authorization remain separate checks.

The [checked local API](10-local-api-contracts.md) now formalizes observation, operation, discovery, preparation, namespace, event and error bodies. A [native Harness overlay](../integration/harness/README.md) exercises it in an isolated checkout.

Absent: remote authentication/per-agent delegation, physical commissioning and adapters, device-enforced leases/timing, bounded-stop path during log failure, isolated adapter supervision, procedure IR and stream/data-reference contracts, event retention/gap recovery, quotas, large-data storage, backups/restore ceremony, remote MCP bindings, production Harness packaging/persistence gates and physical validation. The bounded stop requirement remains outside ordinary journal admission and cannot be implemented by waiting for this journal's writer lock.

The [local MCP projection](../docs/mcp-integration.md) and native Harness overlay use the checked one-attempt client; neither transport identity replaces the daemon principal or durable operation identity.
