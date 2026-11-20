# Original finite synthetic I/O provider: staged executor boundary

Work in this directory is not integrated or tested yet. Execution is on hold while the root agent runs the live checkpoint suite. `baseline/inputs.json` records 49 copied inputs, including the reviewed resource-admission Registry/ResourceCatalog and original Runtime/AdapterCatalog/LocalSimulation/SimulatedPlant. Copying a file is not a full-file reading claim. No previous stage is modified.

## First executable scope

The first provider implements finite `gpio_pulse` and `pwm_burst` primitives in an original SQLite model. An explicit versioned installation contains one bounded topology, its initial generation snapshot, a shared board identity, a route inventory and exact instance/action-to-primitive mapping. It supports multiple actions per instance and multiple routes to the same physical atom. Existing fan/focus/inspection handlers and schemas are not used as executors.

One `SyntheticIoBoard` store is shared by all its routes and bound to one Journal authority ID, deployment, board ID and installation digest. The Runtime owns and opens it once, then passes the same object to route adapters. Opening a second route must never cancel or reset the first route's work. Recovery runs once when the Journal owner epoch advances; reopening a different descriptor/authority or regressing owner epoch refuses before state mutation.

The board retains canonical atom fences and active ownership independently of Journal claims. A new operation requires strictly newer fences; exact receipt replay precedes new fence/session checks and does not execute twice. An adapter independently checks exact installed primitive, typed argument envelope, binding/type/generation, alias roots, resolved atom list and endpoint session. A registry document cannot install code or add an executable route.

Starting a pulse/burst atomically commits active synthetic pin/timer/channel state, ownership and a pending receipt. Completion/cancellation atomically disables PWM, returns affected pads to high impedance, removes only that operation's active ownership and records a terminal receipt with exact safe-idle state. A canceled pulse may already have activated output; it cannot claim `effectCommitted:false` merely because it did not finish its duration. A trusted no-start veto has a distinct receipt and does not advance fences or output state.

Recovery first verifies pending receipt/ownership/fence/state consistency. Only consistent original model state supports an atomic safe-idle cancellation after owner loss. Corruption, contradictory ownership, missing receipt or unknown quiescence keeps the route unavailable and host claims unresolved; it is not repaired by manufacturing an idle receipt. The declared atomic model is not a claim about physical equipment.

## Authority and timing integration

Use the original Journal for admission, dispatch tickets, cancellation, execution/reconciliation and claim release. Its existing dispatch `_reserve` hook records an immutable exact operation/claims/route link in the authority transaction. That link remains after resource release and is compared with provider receipts. An installed evidence validator checks receipt identity, state, exact claims and explicit quiescence before Journal evidence can release resources. Historical binding routes remain authoritative after current binding changes.

The route adapter retains the Journal mutex through the final authority checks and board mutation. It checkpoints the authority clock before effectful work; after potentially slow topology/history/policy validation, it samples wall and monotonic clocks again. A final trusted veto runs inside the board transaction after its lock/BEGIN/read delays. It never extends original start/completion/max-run/lease budgets. Returning to safe idle is allowed despite revoked execution authority or invalid clocks when exact active ownership is established; starting/continuing output is not. No hard bound on SQLite commit completion is claimed.

Native-clock availability and shared-lock latency require later measurements with unchanged deadlines. A fixed-clock test can prove state transitions only. The reviewed catalog currently revalidates full bounded graphs under the authority lock; a future cache must preserve exact installed/generation identity and refusal semantics.

## Mounting path

Introduce an independent I/O installation profile and catalog branch. Stage the Runtime bootstrap so it creates/opens the resource catalog before resource-aware admission, derives all route/instance requirements from trusted saved installation data, provisions exact type/binding documents, opens one board store, and supplies actual adapter `validate_admission` handlers. Do not seed or silently map a fan installation to I/O. Existing installation profile/driver branches remain unchanged. Mixed legacy mounting may be deferred explicitly even though the resource resolver supports legacy claims.

The immutable installation pins initial generations. Admin `publish_generation` alone cannot update the provider's actual generation state or make a new binding executable: a mismatch must refuse. Public Runtime/IPC/CLI/MCP configuration and PAT qualification are not established by an internal staged mount. The fan-only simulation qualification policy does not qualify I/O actions.

## Driver/service lifecycle remains a separate reviewed step

The reviewed admin publication method correctly refuses *all* unresolved claims. An admitted lifecycle operation owns its full affected-instance action footprint, so calling that admin method while holding its own claims would refuse. Releasing claims first is unsafe and explicitly forbidden.

The proposed lifecycle step is a separate admitted instance/action and a receipt-gated settlement transaction. Its installed resolver derives the exact full sibling-expanded footprint plus target lifecycle atom; lifecycle permission is separate from ordinary I/O grants. The synthetic board commits a new service/driver generation and exact operation receipt together. A dedicated authority settlement validates the retained dispatch link and receipt, verifies the operation still owns the complete exact footprint, excludes every other claim in the affected scope, checks expected revision/generation and nonreuse, publishes all affected bindings/proofs, records a unique operation→receipt→publication link, then settles/releases within one reviewed transaction. Repeating the same retained receipt returns the same publication; a different receipt/generation refuses. Crash before provider receipt stays unknown, crash after provider receipt reconciles without reexecuting the effect, and claims remain until authority publication is durable.

That method must reuse existing transaction-internal Registry and Journal transition checks, not weaken `_bind_in_tx` or special-case claims in the admin method. The pure topology profile currently has ordinary access aliases, not executable lifecycle-instance bindings; a separately versioned lifecycle binding/resolution contract is required. Until these contracts and atomic seams are implemented and reviewed, the first provider rejects lifecycle operations. No driver restart, OS management, physical I/O, general hub management or complete user goal is claimed.

## Planned acceptance after the execution hold

Exercise actual original Journal/Registry paths: same-pad GPIO/PWM and raw alias contention, independent pad progress, cross-route fences, exact replay and key collision, malformed/missing/extra fences, wrong sessions/generations/installations, cancellation before and after activation, idle-before-release, crash between board and authority commits, one recovery per shared-board epoch, missing/contradictory receipt retaining unknown claims, and stale authority after slow validation. Retain all source/data pins and per-attempt SQLite/receipt evidence. Lifecycle-specific acceptance remains pending until its separate settlement seam exists.
