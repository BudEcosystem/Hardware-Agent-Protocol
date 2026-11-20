# Receipt-gated synthetic lifecycle settlement

Design only. No implementation, import, test, Runtime, provider, subprocess, model or hardware execution was performed for this artifact. The 15 exact selected input copies are pinned in `inputs.json`; acquisition is not a full-reading claim. `reading.json` records the inspected ranges. The original resource design, its sibling-scope addendum, and the sealed provider remain unchanged. The provider's initial DESIGN describes planned work; its later README/proof records the actual staged result.

## Smallest executable extension

Add one finite, original synthetic operation that advances an installed service or driver generation while leaving every affected pad/timer/channel idle. This models a generation change; it does not restart an operating-system service, load a driver, reboot a hub or establish physical quiescence. GPIO/PWM remain separate installed primitives.

Use a separately installed management instance, with explicitly named actions mapped to fixed target nodes by the trusted installation. One instance may expose multiple target actions. Each action requires its own existing exact-action grant plus read/invoke authority. An ordinary pad grant gives no lifecycle authority. The management instance must not be an ordinary consumer whose binding is among the affected instances. Its stable management binding identifies the installed management implementation and topology, independently of the managed target token. This preserves historical recovery after a target changes and avoids any exception to Registry's same-instance unresolved-claim guard.

Keep `ResourceCatalog.publish_generation` unchanged: it is a quiescent admin configuration operation, and refuses every relevant claim. Add a different, internal settlement path. Neither its public argument list nor a JSON document may contain an `ignoreOperationId`, `allowedClaimOwner` or similar bypass.

The first lifecycle policy remains `refuse_if_busy`. Admission atomically claims the entire sibling-expanded scope; it does not drain, cancel or commandeer existing work. No one-action-per-instance restriction is introduced.

## Versioned installation and exact claim derivation

Existing ordinary `binding_proof(...).expandedClaims[action]` does not derive a lifecycle's reverse-dependent consumer scope. Do not add a lifecycle atom to an ordinary alias and assume this solves the problem.

Introduce a new closed installation profile and explicit lifecycle route requirement, separate from the ordinary resource-root profile. The installation retains:

- An exact management instance/type/action inventory and installed handler identity. Each action maps to one existing service/driver target and the fixed `advance_generation` primitive.
- The ordinary topology/route/handler inventory and stable board/authority identity.
- A distinct recovery/control binding for management, which has no dependency on the generation it changes. Unsupported recursive management targets or management instances appearing in ordinary consumer inventory refuse installation.
- A closed symbolic resource role for each management action. Its resource-map value is an installed lifecycle root ID, never a caller-provided claim list or a string guessed to be an ordinary atom.

The new trusted resolver branch computes `generation_change_claims(topology, installed_target)` for that root. It returns the sorted canonical atoms, including the target lifecycle atom and **all actions of every instance whose combined binding proof changes**. The existing 32-atom cap applies after expansion. Registry's normal argument/grant checks, installed-support check, original Journal admission, resource floors and fencing remain mandatory. Static plan checks and live rechecks use the same derivation; installed support independently verifies target/handler, arguments, exact atoms, current provider generations and management session. There is no flat-ID fallback for a managed instance or route.

Persist both management route and management instance requirements. Omitted/empty constructor inventories, rebinding to another adapter, unavailable resolver and an older implementation must fail closed. A new authority/catalog storage profile is activated atomically with complete installation requirements, so an old Registry cannot silently interpret lifecycle roots as legacy flat resources. Merely opening an old authority does not migrate it. Initial upgrade/provisioning is an explicit quiescent configuration step; it is not repeated for each lifecycle operation.

The closed action input is `{expectedGeneration, newGeneration, expectedRevision}`. The installed action fixes the target; inputs cannot name a different target or widen its footprint. Validate exact bounded identifiers/integers, non-reuse, revision and target token at admission and fresh dispatch. Source/topology/installation replacement remains unsupported. The management endpoint session still changes on owner reopening; historical receipts retain their original session.

## Durable operation and provider evidence

Extend the existing same-transaction dispatch reservation hook to retain a closed `hms.synthetic-lifecycle-dispatch/1` document. It pins authority/deployment/board/installation/management identity, original operation digest and intent, attempt ID and immutable dispatch event epoch, clock/budget origin, target, old/new token, admitted catalog revision, complete scope and exact fenced claims. Also pin every affected current binding and resource proof, the union of relevant dependency tokens, and the historical snapshot used to derive them. Digests are domain-separated, type-sensitive canonical values; retain the bytes as well as digests. Validate every scalar and exact association on reads, not merely a matching hash.

A private provider entry accepts only this retained installed dispatch and the original timing guard. Under the established authority-mutex → shared-board-lock order, it verifies the exact current provider identity/generations, every atom fence and all-sibling idle state. It repeats the current authority/deadline veto after potentially slow validation and immediately before the model mutation. It must not renew the admitted deadline, use a fixed clock as availability evidence or use publication as permission to start an effect.

The synthetic board transaction atomically advances the actual target token, consumes the lifecycle fences, records its generation history and records one exact terminal effect receipt. Receipt fields include the dispatch association, target and old/new tokens, exact fences/scope, provider session, `generationApplied`, explicit idle state for the entire physical footprint, and terminal outcome. No generic `safeIdle:true` flag alone authorizes publication. The board may retain pending intent if the implementation later has multiple steps; absent exact receipt/state agreement, it stays unresolved. The first atomic model needs no fabricated intermediate success.

Receipt replay is checked before new session/generation/fence checks and does not repeat the generation effect. Non-reuse must be verified in provider history as well as authority history. A provider/authority mismatch inhibits fresh dependent I/O until settlement; unaffected scoped bindings may continue. One shared board store/owner epoch remains common to all routes, and mounting a route must not reset it.

## Internal APIs and shared logic

Proposed internal interfaces, subject to review when implemented:

| Interface | Responsibility |
|---|---|
| `LifecycleCatalog.resolve(context, intent, binding, action, live=...)` | Installed lifecycle-root branch, exact scope and token checks; same-authority reads only. Ordinary resolution delegates to the existing ResourceCatalog. |
| `LifecycleCoordinator.reserve(operation, ticket, checkpoint, budget_origin)` | Persist exact dispatch/scope/generation association in Journal's existing dispatch transaction. No provider I/O. |
| `SyntheticIoBoard.advance_generation(dispatch, guard=...)` | One finite original model effect plus exact durable receipt; final timing veto before effect. |
| `LifecycleCoordinator.settle(operation_id)` | Internal lookup-driven reconciliation; obtain provider evidence itself, validate it and atomically publish/settle. Caller supplies no receipt, claim exception, new binding or administrator context. |
| `ResourceCatalog._prepare_lifecycle_publication_in_tx(validated_settlement)` | Derive all new proofs/bindings from current retained topology and the exact admitted change; no writes until every guard succeeds. |

These names are a design, not currently callable APIs. A private validated-settlement object must be created only by the installed coordinator after association, board and claim checks. It is not a security sandbox: trusted Python can access internals. Do not expose object construction or arbitrary callbacks through Runtime/IPC/CLI/MCP.

Reuse Registry's binding validation/publication logic. Its public `_bind_in_tx(owner, binding)` currently combines administrator authorization with validation and writes. Factor a common transaction-internal plan/apply path with the exact existing description/mode/resource/action-schema/history/non-reuse checks and the **unchanged same-instance no-claim guard**. The public bind/admin publication wrappers continue to authorize first. Only the receipt-validated internal lifecycle path may call the common plan/apply without rechecking the submitting user's present administrator grant. It uses retained installed dispatch authority to record a completed effect, not a fabricated admin Context. No direct SQL copy of binding business logic and no generic `skip_authorization` switch.

Reuse Journal `_execution` for transition, historical evidence, dispute, physical-evidence and start-exclusion checks. Extract the existing `release_resources` transaction body into an internal helper, leaving the public wrapper's behavior unchanged. The helper uses the same terminal/non-disputed/quiescence predicates. Settlement must not call public transaction wrappers recursively or directly update operation state/delete claims to imitate them.

## One authority transaction, no claim gap

For an un-settled operation, `settle` acquires the authority mutex, then the shared board lock in the existing order. It obtains a fully validated current board snapshot and exact receipt; it retains that lock through authority commit so another route cannot change the observed model state. Authority evidence callbacks remain pure, bounded same-authority reads; they never perform board I/O. The two databases are not claimed to commit atomically with each other: the already durable board receipt bridges them.

Within one Journal transaction:

1. Load and validate the operation, historical management binding/installed dispatch, immutable dispatch event, receipt bytes and type-sensitive associations. Match the current owner ticket for ordinary recording, or require the existing `outcome_unknown` reconciliation state after owner loss. Preserve original dispatch epoch rather than confusing it with later operation ownership.
2. Recompute the scope from the pinned immutable topology. Require every admitted atom/fence to be exactly owned by this operation, with no missing or additional claims. Check current resource floors and the provider's retained fence association. No other operation may hold a scope claim, and Registry's original per-affected-instance check independently refuses any claim for those instances. The management instance's disjoint identity is an installation invariant, not a runtime caller exemption.
3. Validate the provider's applied token and complete current board consistency/idle evidence, including all siblings. A retained terminal receipt cannot mask unexplained non-idle state, damaged ownership, missing receipts or unknown old hardware state. An unrelated correctly owned operation outside the lifecycle scope is allowed.
4. Validate exact target-before token, affected binding/proof bytes, relevant dependency tokens and historical snapshot association. Validate all next binding plans and token non-reuse. Retain canonical verified receipt bytes in the authority in this same transaction for policy evidence checks.
5. Record truth using Journal's `_record_now` before business mutations. This is reconciliation, so a regressed/unavailable clock is marked explicitly and must not prevent recording an already proved effect; it grants no new execution authority. Fresh admission/dispatch/effect continue to use their original stricter clock checkpoints/vetoes. Never call `_now` after business writes, because its clock-floor commit would break atomicity.
6. Insert the next generation snapshot/token, all changed binding/proof history and current rows; invalidate the affected presences/observations/streams through the shared Registry logic. Apply Journal's normal terminal transition and resource-release helper using the same validated evidence. Insert a unique publication ledger row linking operation, dispatch digest, provider receipt digest, original and settlement base revisions, new revision/token, exact old/new binding-proof digests and terminal/release event sequences.
7. Commit once. Any validation, callback, SQL or commit failure leaves the authority's generation, bindings, operation state and claims together at their pre-settlement state. The board effect/receipt may already exist and is retried through reconciliation, never by reissuing the effect. Unknown commit outcome requires a durable exact-row lookup after reopen.

An exact existing publication row is a separate replay path: verify its closed grammar, receipt/dispatch association, retained generation/proof history and Journal terminal/release linkage, then return the same historical result without a new effect or publication. A different receipt/token for the same operation or a reused token refuses. This historical result does not assert current physical idle, current permission, current bindings or current qualification. A caller-supplied operation ID alone never creates the validated-settlement capability.

## Scoped revision rebase

Keep the existing admin method's global revision CAS unchanged. A lifecycle effect can already be committed when an unrelated admin change advances the catalog revision. Stranding its claims merely because that disjoint change occurred would be avoidable.

The new settlement path may append at the latest revision only if target token, every affected current binding/proof, the full relevant dependency-token union, topology/installation identity and initial dispatch association are unchanged. Derive affected instances and claim closure again; do not trust a stored list to omit a new dependency. Since topology/installation changes are unsupported, any such change refuses. Prove the intervening change is outside this exact dependency/binding scope; preserve its generation values when constructing the next snapshot. No request arguments, target, claim scope or semantic intent are widened.

An unrelated service change is therefore allowed without claiming a hub-wide atom. A change to any affected sibling's combined binding/proof or relevant token refuses and retains all lifecycle claims. The publication ledger records both the original dispatch revision and later settlement base revision. This rebase is an explicit new settlement rule, not a silent relaxation of the admin CAS API.

## Cancellation, recovery and uncertainty

Before dispatch, original Journal cancellation releases accepted claims with its existing no-ticket proof. After dispatch but before a provider effect, only an exact installed start-excluded receipt may settle canceled/rejected and release; no generation publication occurs.

Once the provider commits the generation change, a later cancellation cannot undo it. Settle the actual applied effect and publication, preserving cancellation-request history; do not report an effect-free canceled operation or advance a second generation as an implicit rollback. A failed/no-change receipt with complete idle evidence may settle failure without publication. Partial application, contradictory receipt/state, missing receipt or uncertain old physical effects remain `outcome_unknown` with claims held. An expired deadline or revoked grant blocks new effects but does not erase historical evidence or prevent conservative stop/reconciliation.

Reopening must first load the retained installation/history and shared board sufficiently for recovery even when management or consumer bindings are inactive or current grants are revoked. Fresh work remains inhibited. A lost/changed board store, installation identity or ambiguous owner epoch is not repaired by recreating an idle model. Physical drivers need their own durable receipt, fencing, stop and device-generation guarantees; the atomic SQLite model cannot establish them.

## Implementation acceptance sequence

1. Closed lifecycle installation/dispatch/receipt/publication schemas and pure derivation tests: ordinary roots cannot impersonate lifecycle roots; fixed target/action grants; management/consumer separation; missing resolver/profile and omitted constructor inventory fail closed; overflow, bool/float, malformed digest and unknown field refusal.
2. Original Journal/Registry integration: GPIO/PWM/raw aliases and every sibling action block lifecycle admission; unrelated pads/services progress; exact all-atom fences; foreign/missing/extra claim refusal; authorized management action only. Demonstrate multiple actions on one consumer instance, not only set intersections.
3. Original synthetic effect/receipt integration: one effect on exact replay; generation non-reuse; wrong authority/board/install/session/attempt/epoch/fence rejection; safe idle of all siblings; cancellation before/after effect; timing veto after delayed validation with unchanged budgets. Controlled-clock cases establish logic only; native-clock availability remains a separate measurement.
4. Atomic settlement fault injection at each receipt, generation, binding, event and commit boundary: no released-claims/old-bindings window; current board corruption blocks a valid old terminal receipt; missing evidence keeps unknown claims; changed binding/grant/clock permits historical truth but no fresh execution. Old source opening the new storage profile must refuse.
5. Scoped rebase: disjoint service publication preserves its values and allows exact settlement; changed target, sibling binding, dependency or installation refuses; overlapping lifecycle scopes conflict; dependency-free service still owns its lifecycle atom. Exact duplicate settlement returns one publication and one release event, while altered receipt or history corruption refuses.
6. Port/review only after copied-source proofs pass. Mounting the management route in stock Runtime/daemon/public projections is a later explicit change. Updating installed PAT inventory/semantics and adding a lifecycle outcome policy are separate; the fan-only qualification policy does not qualify I/O or lifecycle effects.

The next implementation files are closed new lifecycle contracts/coordinator modules and their synthetic provider support, a narrow ResourceCatalog publication-planning seam, shared Registry binding-plan and Journal release-body extractions, versioned installation/catalog/storage gates, and focused original integration tests. No generic OS-command hook, user-provided provider, topology hot migration, drain policy, bus executor, standing PWM ownership or physical service-control claim belongs in this first slice. Those remain parts of the broader device/driver/hub and prompt-to-learned-PAT goal.
