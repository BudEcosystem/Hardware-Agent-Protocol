# One coordinated candidate

Prepare a new isolated implementation only after this source scope is reviewed. Keep all public endpoint, transport, runtime and driver signatures/layouts, including `dispatch_report`; preserve the finite/standing common owner and lifecycle. The target, roots, nine storage objects, 160-byte static delta, full uint64 time domain, 512-byte stack reservation and 32,256-byte application allowance remain unchanged. No new persistent scratch, table, descriptor array or generic VM is proposed.

The candidate has two inseparable parts: a byte-oriented private numeric backend and capture-preserving phase kernels that use it directly. Replacing scalar arithmetic in the 2,348-byte helper unit alone cannot close the gap; leaving every caller to reconstruct native wide operands would miss the measured cost.

## 1. Full-domain private numeric backend

Keep the existing scalar read32/read64/write32/write64 leaves and their ABI unchanged, including the generated serializer alias families. Keep published wire bytes and native endpoint/clock fields in their present representations. Replace the private predicate/cutoff arithmetic implementation, not the clock domain, with bounded eight-byte operations:

1. Lexicographic most-significant-byte comparison, returning the same -1/0/1 result for native/native, native/encoded and encoded/encoded operands.
2. Least-significant-byte subtraction with propagated borrow across all eight bytes, retaining the modulo-2^64 result; compare that complete result with the zero-extended uint32 bound. The caller's separate chronological-order check remains separate and in its original position.
3. The exact `value` versus `UINT64_MAX-delta` comparison, and the existing strict-overflow cutoff minimum. Compute addition/carry over all eight bytes and preserve the old saturation policy only where saturation already exists.
4. Pure checked accounting that validates the full elapsed value against remaining uint32 capacity before committing a 32-bit total. The low16 age encoders may use the mathematically equivalent low16 projection of the full unsigned difference; they must not change any preceding full64 freshness or ordering decision.

Use unsigned-character access for native object representations only under a compile-time documented eight-bit-byte, exact-uint64, known-endian backend. For the qualified GCC AVR profile, prove the selected native byte mapping in source and native controls; do not guess it from host endian behavior. A source-compatible scalar fallback remains for unsupported compiler/object representations, selected at compile time. Do not ship both runtime engines, use runtime descriptors, or add an unconditional GNU-only rejection to the portable endpoint API. Native controls must exercise the byte backend as well as its independent scalar reference.

Native and encoded views are private fixed entry points/accessors, not runtime instruction dispatch. Retain each input scalar snapshot before an overlapping output write. Addition/cutoff/age writers that need a new eight-byte local snapshot must charge it to the generated stack path. Predicates make no callbacks, read no clock, and mutate no endpoint or authority state.

## 2. Consolidate contiguous pure phases in all three paths

| Path | Concrete change | Required boundaries |
|---|---|---|
| Finite admission | Capture call/run and the four request timestamps at the existing entry point. Four canonical eight-byte snapshots can replace four native uint64 locals without changing their total 32-byte capacity. One pure pre-guard time-validation phase consumes those captures directly; a separate post-guard time phase reuses them. | Keep describe and its returned metadata validation, resource/commissioning checks, error priority, fences, guard, sample_clock and claim commit in the current sequence. Do not reload the request timestamps after callbacks. |
| Finite ARM/update/poll | Use the same full-domain predicates for existing strict ARM, lease and completion conditions. Keep cutoff-reason selection and report application as distinct phases. | Preserve readiness/context/state priority, captured values, reason selection, before/after driver snapshots and finite terminal evidence. Preserve the existing poll_finite boundary. |
| Standing OPEN/mutation | Consolidate each contiguous lease/time-envelope group into a pure fixed phase using existing captures/encoded bytes. Keep mutation-specific comparisons and duplicate identity checks at their existing statement points. | No common validator may run ahead of syntax, number/revision/digest checks, source binding, refresh/synchronize, ACK rules, counter exhaustion or a lifecycle-specific gate. OPEN and RESUME still commit the same fields in the same order. |
| Standing acquisition | Isolate acceptance into a deliberate private phase that captures sequence/acquired/value immediately on entry and performs the original quality, epoch, gap, time, range and duplicate checks before the shared observation commit. Use encoded acquisition snapshot bytes directly. | The poll calls it only after the driver and post-driver synchronization and only if loss is absent. Do not move captures below report-kind validation or re-read mutable report bytes in place of a capture. |
| Standing freshness/evaluate/feedback | Group contiguous pure age/order/remaining-time checks around unchanged fresh/feedback/transition logic. Compute complete cutoff minima through one phase, with encoded observation timestamps and existing native pre-driver snapshot. | No cache across guard, clock, driver or epoch callbacks. Identity/possible-effect record still precedes the handoff. Strict post-command witness and feedback timing remain. |
| Standing accounting/loss | Reuse full-width checked elapsed/account arithmetic in account_ok and confirmed-quiescence accounting. Keep separate ordinary and loss response/authority paths. | Preserve modulo-duration computation before the loss-service chronological check, existing witness-field writes before a possible counter failure, commit-before-limit-result in account_ok, and final publication of WITNESS_VALID only after valid accounting. |

Pure phase functions should return the original status or compact result needed by their caller. Do not create a retained batch of predicate results, an alternate endpoint-state struct, or a general rule interpreter. Avoid per-scalar wrappers whose only effect is to move eight-byte arguments between registers and stack. Captures remain caller-owned when they span a callback; short-lived intermediate arithmetic belongs inside its phase.

## 3. Selective generated boundaries, with explicit charges

Keep the current finite handler/poll boundaries. Deliberately retain observation acceptance as a private call boundary to contain the measured acquisition temporaries. Keep existing loss_service/feedback/evaluate boundaries; consider an independent cutoff phase only as part of this coordinated backend, so that evaluate does not recreate the full encoded/native chain. Preserve one 32-byte report owner in poll; do not add a second report or retain a pointer past its lifetime.

Use the existing conditional GCC qualification convention for sharing/noinline. Verify one emitted body, caller setup, outgoing argument area, nested save frames and clone/alias behavior after LTO. Attribute a result to the combined candidate, not imaginary per-edit savings. An extra call can cost more than the spills it removes, and pointer/byte access loops can add address arithmetic.

Do not add blanket noinline to runtime/clock/boot/public functions. The observed ten retained-root copies and unique startup work do not substantiate a large duplicate-code deletion. The candidate may keep those paths byte-for-byte source unchanged while its full-image measurement charges all compiler changes to them. A later runtime phase proposal requires its own precise liveness evidence and callback proof.

## Full-gap acceptance and stopping rule

The future diff must include the coordinated finite, standing handler and standing poll phase changes above, their arithmetic proof and meaningful controls. Merely replacing one helper or moving one copy is not this proposal. Existing helper ABI stays; new functions are private implementation detail, with no root removal.

Run the already bounded owned native and AVR LTO stages only after their exact source and runner are reviewed. Retain all failures. Measure the complete map against 39,902, all aliases/roots/storage, new helper/library allocations and caller code. Successful native equivalence is necessary but not sufficient. Any remaining link overflow leaves the unchanged profile unsupported.

There is no credible numeric savings forecast in the retained evidence, and no proof that the remaining 7,646 application bytes are removable under these constraints. The combined candidate is the next large architecture-preserving experiment, with a concrete stop decision: if it still does not fit, retain that result and derive any further refactor from the new whole-image evidence. Do not present successive small reductions as qualification. A valid linked image would still need complete stack/ISR/callback accounting and physical driver qualification before deployment claims.
