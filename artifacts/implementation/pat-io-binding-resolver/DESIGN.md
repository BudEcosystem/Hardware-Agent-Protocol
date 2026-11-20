# Trusted finite-I/O PAT binding resolver — design only

Propose a separate `IoRegistryPatBindings` in a new `hms/pat_io_bindings.py`. Keep the existing `RegistryPatBindings` source and legacy route semantics unchanged. This document and its copied inputs do not implement or execute that resolver. The staged fixed-unit compiler has a separate pure34 pass; it is not integrated live and does not qualify I/O.

The baseline is the exact 151-input full748 snapshot. The preceding I/O PAT design and its 22 selected historical input copies are retained separately, without relabeling them current. The fixed-unit candidate compiler/test and actual pure34 proof are also pinned. The proposed resolver fills only the trusted discovery/metadata join. Strict whole-domain timing, an independent I/O worker/oracle, evidence/catalog integration and the trusted service remain separate obligations.

## 1. Interface and authority boundary

Use the existing resolver interface:

```text
IoRegistryPatBindings(runtime, registrations)       # trusted application setup
resolver(context, artifact, request)                # complete static enumeration
resolver.for_roles(context, artifact, role_instances) # explicit trusted qualification assignment
resolver.registration_identity                     # immutable digest
```

Construction accepts trusted local objects, never a public run-request field. Require one shared Journal/Registry/catalog/resource-catalog authority. Copy and validate the full installation from the explicitly selected I/O catalog; do not construct or reopen an adapter, catalog, board or Runtime. `normalize_installation` and `definitions` may be used during trusted setup, including their source-identity reads. Freeze the normalized bytes, full installation digest, derived route/type/initial-binding definitions and explicit semantic registration. No source hashing, provider callback or filesystem read is needed during selection. Changing files underneath an imported deployment is unsupported; a new implementation requires fresh trusted setup and identities.

Each call first acquires the Journal's existing reentrant mutex and then requires an already-active transaction and matching deployment. Acquiring that mutex before checking `in_transaction` prevents a different thread's transaction from satisfying the check: the other owner must finish before this thread acquires the mutex. The resolver does not begin, commit or roll back a transaction, call `_now`, sample a clock, refresh presence, allocate keys, reserve claims, execute an operation or touch the board database. All SQL is SELECT; `total_changes` and transaction state must be unchanged. The existing PatExecutionStore purity check remains in place. This trusts the existing single-owner Journal transaction discipline, not hostile direct connection access.

The `request` cannot narrow the installed inventory or supply semantic metadata, driver identity, a chosen instance or a callback. Ordinary selection returns only the existing closed `{complete: true, assignments: [...]}` form. It raises on indeterminate inventory; it never returns a partial list labeled complete. `for_roles` is explicitly trusted setup, does not assert uniqueness, and validates each chosen role through the same current-binding checks. It is not mounted as a public request option.

## 2. Explicit primitive semantic policy

Freeze policy identifier `hms.pat.bindings.sqlite-finite-io/0.1`. Retain the six existing registration fields: `instanceId`, `typeDigest`, `driverProfile`, `driverDigest`, `installationDigest`, `argumentMetadata`. The outer registration list contains 1..128 unique installed instances, is bounded as a whole by the existing 65,536-byte canonical carrier, and contains only built-in JSON values. Per-instance argument metadata is capped at 16,384 bytes and 32 actions. Unknown fields, duplicate entries, unknown registered instances and wrong scalar types refuse.

Only `sqlite-finite-io/1`, the trusted full installation's exact source digest and its full already-prefixed `sha256:` installation digest are accepted. This differs from legacy installation digests, where the old resolver adds the prefix; do not prefix the I/O digest twice or substitute a route hash.

Determine semantics from the normalized installation's closed handler record `(instanceId, actionId, primitive)` and the matching type/binding schema. Action names are arbitrary identifiers. A fixed code policy for those exact primitive schemas supplies the following required registration, without conversion:

| Trusted primitive | Argument | Fixed unit |
| --- | --- | --- |
| `gpio_pulse` | `level` | `1` |
| `gpio_pulse` | `durationMs` | `ms` |
| `pwm_burst` | `frequencyHz` | `Hz` |
| `pwm_burst` | `dutyPermille` | `permille` |
| `pwm_burst` | `resolutionBits` | `bit` |
| `pwm_burst` | `durationMs` | `ms` |

Every entry has the exact staged five-field form `{profile: "hms.pat.argument.fixed-schema-unit/0.1", unit: <above>, frame: null, unitArgument: null, frameArgument: null}`. This is an explicit schema policy for known handler primitives, not guessing units from arbitrary argument names. Verify supplied trusted registrations against the expected policy; do not synthesize missing registration during enumeration. Do not accept a fan type or relabel a legacy action. Preserve the exact installed schemas, including the timer envelope and resolution. No duration bound is silently narrowed in the descriptor.

The registration identity hashes a closed, versioned body containing the policy profile, full installation digest, driver source digest and sorted explicit registrations. Metadata also enters the existing compiler metadata/environment digests. Adding this module or changing compiler bytes changes the conservative `implementation_digest()` project closure: old driver/installation/evaluation pins do not remain current. The compiler's separate five-package optional-dependency identity gap is not repaired by this resolver design.

## 3. Complete bounded inventory and pre-fetch rules

Use a local, constant-schema point-read wrapper around the existing `_resource_stored_row` pattern. It performs storage-type checks first, byte-length checks second and body fetch last while the same Journal mutex/transaction remains held. Table/column/key specifications are internal constants, not document strings. Blob documents are 1..65,536 bytes, identifiers/profiles at most 128 ASCII identifier bytes, prefixed digests exactly 71 bytes, raw hashes exactly 64 bytes; digest syntax is checked after bounded fetch. Integer fields require SQLite `integer`, exact Python `int`, allowed ranges, and exact 0/1 flags where specified. REAL/TEXT/BLOB flags and out-of-range integers refuse. Canonical JSON bytes, typed schemas and exact associations must all match; canonical equality alone is not permission to normalize a `1.0` token into an integer.

Do not call legacy `_type`, `_instance`, `_binding` or `_meta` first and only measure the fetched body afterward. Preflight the exact rows before invoking any existing helper that would fetch them again. Within the held transaction the preflighted row cannot be swapped by another Journal user. No broad rewrite of legacy Registry/PatExecution storage reads is proposed; their unrelated read paths are not covered by this new resolver's bound claim.

The call validates these layers in order:

1. **Profiles and full installation.** Read minimal Registry version/deployment and I/O catalog metadata with type/length bounds. Require the resource-aware Registry profile and exact `hms.adapter-catalog/io/1`. Count singleton tables with bounded `SELECT 1 ... LIMIT 2`, so extra rows refuse before documents are fetched. The full stored installation must be canonical and byte-identical to the frozen trusted normalized document, with the exact full installation digest. No legacy fallback or shape-based auto-detection.
2. **Every route.** Derive expected route records from the trusted full installation, not from caller filters. There are at most 16. First count literal rows with `LIMIT 17`, then point-read each known adapter. Require exact profile, adapter, board, full-installation digest, list of instances, canonical bytes and raw route digest. Unknown, missing, duplicate/replaced or extra route inventory refuses; a bad route cannot be silently skipped before driver filtering. Ready flags are typed 0/1, with not-ready handling deferred until an otherwise eligible instance is identified.
3. **Managed resource inventory.** Use the existing read-only ResourceCatalog `_load` after preflighting its legacy Registry metadata dependency. Verify exact retained topology/routes against the full installation and all current generation/token associations. It already requires exact route/managed-instance inventory and bounded current document reads. The complete installation has at most 128 handler records, hence at most 128 distinct installed instances. Unmanaged arbitrary Registry entries are not candidates; a managed instance cannot escape by rebinding to an unregistered route.
4. **Minimal instance and authority facts.** For every installed instance relevant to a role, read bounded identity/state fields: instance id, deployment, expected type digest, simulation identity kind/reference and exact retired flag; read the current binding's typed active flag and generation association. The expected enrollment reference is the catalog's exact `io-installation:` identity derived from the full digest and instance. Only trustworthy identity/state permits retired or inactive exclusion. Check exact read plus each required invoke grant via existing literal-row authorization queries. Unauthorized instances are excluded without revealing their bodies; malformed identity/state is not a no-match shortcut. For missing otherwise-compatible rows, known installed identities and grants are sufficient to classify authorized missing state as indeterminate.
5. **Current type/binding/proof join.** For each authorized compatible active instance, preflight current type and binding bodies, their digest/generation columns, retained binding history, resource proof and its referenced generation snapshot. Validate the type digest and canonical bytes against the trusted handler-derived type; validate every binding field against both its current SQL identity and retained history. The history binding hash, proof's binding hash, proof document digest and generated proof must agree. Require proof revision 1..current revision. Before invoking `_retained_proof`, parse the already-bounded historical binding and prove its type digest equals the expected preflighted type. This prevents a corrupted historical type reference from directing the helper to an unbounded different type row. Preflight that exact type before `_retained_proof`/`_validate_binding` can read it through the legacy helper. A changed type/capability/action cannot first be used to hide a damaged candidate: compatibility is based on the validated installed definition.
6. **Current support and metadata.** Recompute the instance proof using current generations and require the entire scoped proof to equal the retained binding's proof. Require the current binding to equal the immutable provider's installed definition. Check route readiness and exact semantic registration; `_binding` then validates the compiler descriptor against the role requirement. Do not call the board's `supports_binding` or `validate_admission`: the ordinary provider's exact immutable support predicate is reproduced by equality with the same trusted definitions, with a source guard/regression documenting that contract.
7. **Session provenance.** Read a bounded presence row, require its adapter to equal the binding route, validate the session identifier and bounded integer expiry, and join the same session to `reg_endpoint_sessions` plus the retained session-history existence row. Missing or contradictory session provenance for the eligible candidate is indeterminate. Do not compare expiry to a newly sampled clock, refresh the row, fabricate a session or consult board state.

Global catalog/route/resource inventory corruption aborts completeness even if it cannot yet be attributed to one candidate. Candidate-specific missing metadata/session/not-ready/unsupported current binding aborts when that instance is otherwise authorized, statically compatible and active. A genuinely validated different driver/capability/action, valid retired/inactive state or denied authority may be excluded. No resource contention, observation age, current electrical state, busy board or effect history is used to select a different alias.

Counts use bounded literal rows before fetching keys/bodies; point queries use already-validated expected keys and `LIMIT 2`. Historical generations/proofs are point-read only, not scanned without bound. Existing topology limits remain: 128 nodes/atoms/consumers, 256 aliases, depth 16, 32 expanded claims per action. Finite host fetches do not establish SQLite internal memory/time bounds or hard filesystem quotas.

## 4. Generations, sessions and replay

An unrelated generation update can change the catalog revision while leaving this instance's proof and binding exactly unchanged. Allow that unchanged instance; do not reject all routes merely because `current_generations_supported` is false or because the global generation map differs from initial installation. The proof's dependency closure intentionally excludes unrelated generation changes.

A relevant current generation change changes the binding/proof. The ordinary immutable provider still supports only its installed definition, so this authorized compatible candidate is **indeterminate/unsupported**, not removed from the inventory. Do not manufacture a rebased installation or borrow the unexecuted lifecycle stage's generation-view rules. Supporting later lifecycle execution needs a separately qualified provider contract.

Expired presence may supply a checked retained session for static descriptors. That makes no assertion of current availability or permission to start. The compiler keeps the session in run dependencies while excluding it from the evaluation environment. PatExecution's later `validate_bound` still checks actual installed plan support; primitive admission and handoff still enforce freshness/session continuity. The resolver does not weaken those checks.

Existing PAT exact replay checks retained run/key identity before fresh selection, so a historical repeat must not call this resolver or choose a new binding. Preserve that order. No descriptor is rebound to a new session/generation for replay, and historical receipt access is not fresh qualification.

## 5. Assignment/output bounds and error behavior

Parse the artifact through the unchanged bounded PAT grammar (at most 16 roles). Build sorted candidate identity lists from the complete inventory, validate eligible descriptors and only then compute the Cartesian product. Preserve at most 16 assignments per artifact and the existing PatExecution aggregate cap of 128 across the catalog. Overflow refuses; no truncation or first-match shortcut. Shared resource aliases remain distinct instance candidates; choosing the same instance for two roles is not implicitly prohibited by this resolver.

Cache immutable trusted setup data and call-local bounded rows only, never an authorization, presence, current-binding or eligibility answer across calls. Defer descriptor deep copies until assignments are emitted; cap each descriptor/assignment by the existing 65,536-byte carrier, and the sum of emitted assignment bytes by 16 times that bound. Bound cached distinct installed descriptors by 128 entries/8 MiB; oversize refuses rather than dropping an instance. Return detached descriptors with metadata restricted exactly to the role's required actions. No invented origin time, sample parameter value, replay namespace or operation key is needed.

Use stable `JournalError`/`PatError` refusal categories for malformed storage, changed installation, missing registration/session, unsupported installed binding and enumeration/output bounds. PatExecution already turns resolver exceptions into `PAT_BINDINGS_UNAVAILABLE`; that remains indeterminate and prevents false uniqueness. `complete: true` with an empty assignment list is reserved for a validated inventory with no eligible assignment. `for_roles` uses the same global inventory and chosen-candidate checks but intentionally does not claim complete search or uniqueness.

## 6. Source plan and acceptance gate before any execution

Proposed implementation touches only new staged `hms/pat_io_bindings.py` and `tests/test_pat_io_bindings.py`, plus exact copied prerequisites. The reviewed fixed-unit compiler is the explicit compiler delta in that copied project. Preserve the legacy `hms/pat_bindings.py` and its tests byte-for-byte. No Runtime factory, API/CLI/MCP, service configuration, board, provider, worker, reducer or catalog mounting is part of this slice.

Planned cases, not executed here:

- Explicit GPIO/PWM handler metadata, opaque action names, all five unit labels, exact full installation identity and driver source identity; missing/wrong units, wrong tag/fields, bool/float and registration aliases refuse.
- Two authorized cross-route aliases remain two candidates; read/invoke revocation filters only that instance; incomplete registration/session or unsupported current generation for the other authorized compatible alias refuses the entire enumeration.
- Expired presence and held claims preserve the same candidate set without refreshing, sampling clocks or inspecting the board. An unrelated generation change preserves an unchanged binding; a relevant generation change refuses unsupported immutable execution. Valid inactive/retired instances are excluded only after trusted state checks.
- Exact stored route/full-installation/type/binding/resource-proof joins; dropped, duplicated, replaced or extra inventories and damaged profiles fail closed. Tampered ready/active/retired flags cannot become truthy Python booleans.
- Row-factory/SQL-trace probes prove wrong storage classes, oversized metadata, oversized BLOBs and over-count inventories are rejected before host body materialization. Include multi-byte TEXT length, REAL flags, out-of-range revision, missing proof/history/token and a future proof revision.
- Per-call read-only authorizer plus `total_changes`/transaction-state checks; no own transaction or provider/board/clock call; caller-owned transaction and deployment required; another thread's held transaction cannot authorize an unlocked call.
- Exact 16-assignment boundary, 17-assignment refusal, aggregate descriptor/output limits and detached input/output identity. No per-role truncation, no request-supplied inventory narrowing.
- Pure environment extraction and lowering preserve the full declared schema and explicit caller-supplied times/keys. Duration 5000 stays in the installed schema; this resolver does not falsely claim it fits the board's strict 5000-ms execution bound.
- A later isolated original-SQLite integration gate must prove exact historical PAT replay bypasses changed resolver availability and leaves business rows/effects unchanged. That execution needs separate authorization and an actual I/O qualification oracle; do not fake fan evidence to make a PAT run eligible.

Before implementation, root reviews this interface, bounds, join order and test plan. Before any tests, freeze the copied source/dependency closure and obtain the separately scoped execution release. No claim of I/O-qualified PATs follows from this design or the earlier pure34 run.
