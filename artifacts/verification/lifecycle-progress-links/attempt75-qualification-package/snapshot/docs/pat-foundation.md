# Parameterized PAT compiler and promotion catalog

The [main-runtime integration](../artifacts/implementation/runtime-pat-foundation/README.md)
passes all 861 tests. Compiler identity now uses the explicit `/0.2` profile and
digest domain, bounds acquisition of seven selected dependency packages and
supports trusted fixed-schema unit metadata. Existing qualification retains its
original identity; this change does not silently repin historical artifacts.

The separate [qualification package candidate](../artifacts/implementation/qualification-package/README.md)
removes flat-module imports and pins both package initializers in the worker
image. Its actual full qualification hit the original deadline after writing
25 case manifests; it published no qualification evidence or application.
Package checks and catalog controls are narrower evidence. It is not mounted
in the public runtime, and the existing full 861-test source is unchanged.

Status: experimental host libraries, 2026-11-07. The typed compiler and local
catalog implement part of the [prompt-to-PAT architecture](prompt-to-pat.md).
[Deterministic structured selection and atomic instances](pat-execution.md) now
extend them. These libraries are not yet mounted as Runtime, CLI or MCP methods.
Production evaluation policies, prompt synthesis, trace learning and persistent
applications remain required.

## Artifact and lowering

[`pat_contracts.py`](../hms/pat_contracts.py) accepts immutable bounded
`hms.pat/0.1` artifacts using `hms.pat.bound-sequence/0.1`. One artifact declares
its task/input profile, named parameters, capability roles, static applicability,
one to sixteen ordered steps, timing/effect limits and simulation outcome scope.
Changes produce a new domain-separated digest. Friendly names and versions are
metadata, not mutable execution pointers.

Parameters use bounded integers, booleans or bounded strings, optionally finite
enums. Integers carry explicit units and optional coordinate frames. Argument
expressions are tagged literals or parameter names. There is no interpolation,
code loading, property traversal, branching or loop execution. Unknown fields,
dynamic observations, sustained guards and unsupported effects are refused.
Boolean and integral-floating inputs do not become integer parameters through
canonicalization. Every parameter and declared role/action must be used.

[`pat_compiler.py`](../hms/pat_compiler.py) lowers a validated artifact with
explicit parameter values, role bindings, time origin, deadline and replay keys.
It checks the entire parameter domain against both type and binding argument
schemas, not just the current sample. Semantic metadata explicitly identifies
unit/frame companion arguments; no conversion or meaning inferred from argument
names is allowed. The compiler validates consistency of the supplied type,
binding, calibration, control and metadata snapshots and records caller-declared
driver and installation digests. It does not fetch or rehash installed driver
binaries or inspect live commissioning state. It never generates a
fresh key or reads the clock during compilation.

The output contains a complete existing procedure request, its digest, a
compatibility report, the artifact/compiler identities, an evaluation environment
and a separate run-binding digest. Endpoint session belongs to the run binding;
the evaluation environment pins the static compatibility closure. The compiler
identity includes the implementation source hashes and installed validation
dependency file closures. Module import is its identity snapshot boundary;
changing files underneath an imported deployment is unsupported.

Binding snapshots and semantic metadata come from trusted callers. Parsing them
does not authenticate their source or establish that hardware is commissioned.
The normal procedure and child-operation admission checks remain mandatory.
The first profile is explicitly simulation-only and preserves installed primitive
guards; it cannot lower a standing thermostat or arbitrary continuous invariant.

## Catalog and evidence authority

[`pat_catalog.py`](../hms/pat_catalog.py) uses the Journal's authority database and
transaction lock. Eight versioned tables retain immutable artifacts, evaluations,
decisions, per-deployment entries/revisions and events. A partial table set or
unsupported version fails closed. The first catalog admits at most 128 distinct
artifacts per deployment and returns an explicit limit refusal when full.
Retired entries count toward that limit. Evaluation, decision and event history
has no retention or byte bound here.

All current methods require the registry's existing administrator grant. This is
a trusted management library; ordinary device invocation grants do not authorize
publication or promotion. No caller JSON can provide an evaluation result.
`Evaluator` registrations are installed code with pinned implementation/policy
identities and explicit required positive, boundary, negative and fault cases.
Those identities are trusted registration labels; the registrar must bind them
to the actual installed evaluator code and policy.
The evaluation callback runs outside the authority transaction. The enabled,
environment and compiler-identity callbacks run inside it and must be trusted,
bounded, pure and non-reentrant. Authority and evaluator availability are checked
again when committing the result.

The service constructs receipts from those results. Committed results retain
failed, inconclusive and malformed outputs. There is no durable in-flight record
before the evaluation callback: process loss or a commit-time authority refusal
can leave no evaluation receipt, and an uncommitted callback can run again.
A malformed result or evaluator exception
records unknown unresolved effects and cannot qualify an artifact. A passed
receipt requires every policy-required check and every additional attempted
check to pass, with zero unresolved effects. Receipts pin the complete artifact
domain, compiler, tested environment, evaluator policy, individual evidence
digests and declared limitations. The trusted evaluator remains responsible for
actually running and preserving the referenced tests; these hashes identify
evidence and do not authenticate it. The catalog tests use explicit synthetic
evaluator fixtures, not a completed production qualification policy.
Pinning the complete declared parameter domain does not prove that evaluation
exercised every value. The tested environment is the trusted provider's declared
snapshot.

Promotion requires a valid, nonregressing Journal host-clock reading and the exact expected catalog
revision. In one transaction it checks the current compiler/environment/evaluator,
records a decision, updates the active entry and increments the revision/event.
Every new evaluation increments that revision. New evidence suspends an active
entry, including a later passing evaluation, until an explicit new promotion
decision is made. Once a new evaluation commits, an old promotion cannot silently
continue eligibility. An evaluation still running outside the transaction does
not suspend the existing active entry.

Evaluation run identifiers deduplicate committed evaluations. Replaying an old
successful evaluation does not replace a newer failure. Retirement cannot be
reversed. Conflicting concurrent results for one evaluation key are both retained;
the conflict suspends reuse and prevents promotion until a distinct new evaluation
is committed. Duplicate conflict evidence does not increment the revision again.
Eligibility is recomputed during describe, snapshot and promotion calls against
current dependency and evaluator identities. The separate execution store checks
eligibility again when admitting new instances. There is no watcher, and a
dependency change does not itself change the stored active state.
Suspension/retirement remain possible when the clock regresses or an environment
provider fails. Decisions declare `retain_pinned_version`; the execution store
retains admitted instances and delegates cancellation to the procedure engine.

## Execution integration and remaining work

`PatExecutionStore.run` chooses a unique evaluated artifact and authorized role
assignment before considering transient resource contention. It links the durable
trigger, bound instance and procedure in one transaction. The implementation and
its current limits are described in the [execution profile](pat-execution.md).
Public tool projections and production evaluator/provider configuration remain
unfinished.

The [qualification components](pat-simulation-qualification.md) now add an
actual isolated fan worker and an optional retained-evidence verifier. A configured
verifier runs inside eligibility checks after exact environment matching; invalid
or unavailable evidence blocks promotion and new selection. Legacy registrations
retain their old identity shape. The bounded evidence store and durable attempt
supervisor are not yet mounted, so the catalog's synthetic test evaluators remain
distinct from a usable installed qualification service.

The existing [procedure engine](bounded-procedures.md) remains the executable
lowering target. [Device I/O, drivers and hub control](io-driver-hub-control.md),
stream/material provenance, standing event applications and qualified endpoint
controllers remain separate required implementations. Passing these host tests
does not demonstrate physical control, zero-inference prompt interpretation, learned
promotion or completion of the user's full objective.

The [independent catalog review](../artifacts/verification/pat-catalog-review/README.md)
retains twenty adversarial tests and six process-loss cases, including conflicting
evaluation races and revision exhaustion. The [latest runtime attempt](../artifacts/verification/local-runtime-current.json)
identifies the current result; the [last successful receipt](../artifacts/verification/local-runtime.json)
records a complete regression suite at its pinned inputs. The previous
[369-test baseline](../artifacts/verification/runtime-369-snapshot/index.json) remains frozen.
