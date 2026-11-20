# Deterministic PAT selection and atomic instances

Status: experimental host library. `PatExecutionStore` adds structured-trigger
execution to the [PAT compiler and catalog](pat-foundation.md). It is not yet
mounted as a Runtime, CLI, MCP or native Harness method. Prompt interpretation,
learning, production qualification and persistent MCU applications remain open.
The [progress record](../PROGRESS.md) distinguishes focused checks from complete
regression results and physical validation.

## Request and selection

An installed caller supplies a closed `hms.pat-run/0.1` request with
`replayNamespace`, `runKey`, `taskKind`, `inputProfile`, typed `parameters`,
`evidenceMode: "simulation"`, `originUnixMs` and `latestCompletionUnixMs`.
The caller does not supply a driver descriptor, evaluation result or arbitrary
program. The current profile uses bounded scalar parameters and finite ordered
steps. Integer parameters remain distinct from booleans and floating values
before digesting or replay lookup.

The router considers active artifacts with the requested task/input profile and
applicable parameter domain. Installed binding providers enumerate complete role
assignments. Exact read and action authority, static support and compatibility,
and equality with the passing evaluation's environment determine eligible pairs.
Exactly one artifact-and-assignment pair must remain. Zero matches and ambiguity
produce distinct refusals. Similarity scores and model calls play no part here.

The router does not use busy resources, current sensor values or expired presence
to choose between otherwise eligible pairs. A blocked device cannot make another
PAT the unique semantic match. An unavailable evaluator or incomplete provider
answer is an indeterminate refusal, not an absent candidate. The current profile
allows 128 catalog artifacts, 16 assignments per artifact and 128 assignments
across a search; exceeding a bound refuses rather than truncating the inventory.

An artifact evaluated for one concrete binding does not thereby qualify another
device. The compiled environment must equal both the passing receipt and the
current trusted environment. Authorization and equality with the tested binding
are checked before querying that binding's environment service, so an inaccessible
deployment cannot block a separate authorized match.

## Installed metadata and authority

[`RegistryPatBindings`](../hms/pat_bindings.py) joins current type/binding rows with
the runtime's installed adapter maps and explicit semantic registrations. Each
registration pins an instance/type, driver profile and declared digest,
installation digest, and argument units/frames. It performs no driver loading,
device refresh, name-based unit inference or conversion. Driver identity labels
and semantic registrations are trusted installation inputs, not binary attestations.

A compatible, authorized installed device without required metadata makes
enumeration incomplete and refuses. Raw registry entries outside the installed
adapter maps are not executable candidates. The current adapter maps support the
two existing simulation drivers; this does not install GPIO, buses, OS drivers or
GPU management providers. An expired presence row may supply its retained session
identity, but never proves current availability. A missing session is uncertainty,
not permission to select a different device.

Fresh PAT execution reuses existing per-device read and exact action permissions.
It grants no new device authority. Publication and promotion still require the
catalog administrator permission. A scoped nonadministrator can compose only
actions already authorized to that principal. Current child admission and every
handoff retain the existing live policy checks.

## Atomic identity and recovery

The owning namespace and trigger key are looked up before current catalog,
environment, resolver or clock checks. An exact retained request returns the same
instance after owner/current-read checks. A changed request conflicts. A pruned
namespace cannot revive an old trigger. A new trigger is an explicit new run;
neither lookup failure nor uncertain effects silently generates a replacement key.

For a new run, one Journal transaction performs selection, pins its evidence,
creates the procedure and reserves its keys, then inserts the PAT instance and
trigger link. The existing procedure admission logic is shared through a private
transaction helper. No nested transaction or duplicate admission implementation
is used. A new PAT cannot adopt an existing plain procedure with the same key.

The run key is the procedure key. Child keys derive deterministically from the
namespace, run key, artifact digest and step identifier. The durable record pins
the original request, parameters, artifact, evaluation, promotion decision,
compiler/dependencies, exact compiled procedure, registry/catalog revisions and
selection inventory digest. The inventory records what the trusted resolver
enumerated; it does not independently attest completeness of arbitrary callback
code. An explicit resolver registration identity is retained when available.

The compiler identity also covers the catalog, execution and binding-provider
implementations. Its module-import snapshot boundary remains explicit: replacing
source files underneath an imported deployment is unsupported.

Status verifies the stored procedure linkage and reservations. Resume and cancel
reuse procedure ownership and current permissions. Restart interrupts automatic
continuation, requiring explicit resume. Catalog suspension inhibits new instances;
already admitted instances retain their pins, while current device authority and
live guards still apply. Withdrawal is not a claim that an actuator stopped.

The authority clock checkpoint precedes business writes. Procedure, reservations,
instance and trigger then commit together. This is software identity atomicity;
physical effects remain governed by separate endpoint receipts and reconciliation.
Callbacks are trusted bounded, pure code. Mutation checks catch some programming
errors but are not an in-process sandbox or a hard execution-time bound.
