# Proof obligations

These are implementation obligations, not a claim that an unwritten candidate has been verified. All 64 bits remain significant, including high-bit ticks and UINT64_MAX. ABSENT remains a caller policy and cannot be collapsed into an arithmetic special case inside a generic predicate.

## Arithmetic

For an unsigned eight-byte value, most-significant-first digits form a base-256 expansion. The first unequal digit determines numeric order. Native-object byte access must map those digit positions exactly; canonical wire values already use this order. Unsigned-character access is permitted for object representation, but native endian mapping must be explicit and supported, never inferred from a cast to an encoded pointer.

For subtraction, at each least-significant-first digit compute the digit difference and incoming borrow, emit the residue modulo 256 and propagate a borrow of zero or one. By induction, after digit k the emitted suffix equals the low 8k bits of the original unsigned subtraction; after eight digits it is exactly subtraction modulo 2^64. Discard the final borrow exactly as uint64 subtraction does. Compare all eight result bytes with the zero-extended uint32 bound. Testing only the low32 or assuming chronological order would be wrong. Keep any original chronological-order test and its refusal priority separately.

Addition uses the corresponding eight-digit carry induction. `UINT64_MAX-delta` comparison must preserve <, <=, > and >= exactly. Existing cutoff saturation uses `base < UINT64_MAX-delta ? base+delta : UINT64_MAX`, including its equality behavior. Ordinary scheduling currently rejects at `>=`; do not replace that with the cutoff rule. Neither helper may introduce signed overflow or rely on AVR signed-int promotions; all digit intermediates must have explicit safe bounds.

For accounting, old total is uint32. A nonnegative chronological duration is eligible only if the full64 duration is at most UINT32_MAX-total. Only after that check can the sum be represented as uint32. The existing account_ok commits when requested before returning whether total is below max_on_ms; preserve that state change even when its return is false. Loss service computes its unsigned duration before checking temporal order, then may have already copied witness fields before failing accounting. Preserve those statement-level effects; do not turn it into an all-or-nothing transaction.

Low16 age encoding is `(uint16_t)(end-start)`. Projection modulo 2^16 commutes with unsigned subtraction modulo 2^64, so its emitted two bytes can be derived from the low16 difference. This equivalence does not authorize narrowing end/start for any validity, freshness, dispatch, lease or accounting check.

## Capture, alias and write order

Finite admission originally captures call, run, nb, latest, complete and lease before metadata callbacks. The canonical snapshots must contain those exact original values in the same capture sequence, even if the request aliases state later modified by a callback. Captures remain valid across describe, guard and sample_clock; a later reread is not equivalent. Do not increase those four timestamp snapshots beyond their existing 32-byte logical capacity without explicit stack accounting.

Observation acceptance captures sequence, acquired and value before examining report kind, while old sequence is read at its original point. The refactor keeps that order and captures even for a subsequently refused report. It cannot inspect a partially overwritten report or move the old-sequence read across a state mutation.

Pure comparisons may inspect operand bytes without mutating them. Every scalar-to-output helper must snapshot its entire original source before its first output write where the old by-value calculation did so. Keep per-field read/write order in serializers; do not snapshot an entire endpoint early or merge separate stores. Keep the existing memmove calls for overlapping encoded timestamp copies. Preserve the alias-sharing scalar serializer leaves; if generated ICF changes nevertheless, charge every resulting allocation.

## Authority, callbacks and errors

No pure phase kernel calls describe, guard, epoch, clock or driver. It must not mutate callback_active, flags, state, ownership, fences, counters or records. A phase return is applied only at the original statement point. Moving a check ahead of a callback or combining checks that currently produce distinct statuses is a semantic change even when ordinary success is unchanged.

Finite admission preserves: duplicate/old/context/readiness/state/busy gates; describe; metadata/resource/commissioning checks; initial time errors; fences; guard; fresh clock; readiness/state/context; post-guard time errors; serialized operation/fence/receipt commit. ARM preserves its existing readiness/context/state ordering, strict future expiry and horizon bounds.

Standing OPEN and mutation retain syntax, transport/session, standing number, identity/digest, expected revision, mutation envelope, duplicate and response counter order. ACK still refuses FEEDBACK_INTERRUPTED until valid aggregate quiescence and never converts unknown handoff into known settlement. Shared finite/standing admission and retained claims cannot be bypassed by a new helper.

Acquisition remains potentially effectful I/O: the driver checks actual authority and cutoff at handoff, then clock/synchronization/source binding are refreshed before acceptance. Transition retains activation identity and possible-effect record before the driver. Dispatch ABI and before/after/cutoff arguments are unchanged. Observation witness time must be strictly after actual loss handoff; loss-start time is distinct. The private QUIET_AT handoff alias stays unpublished until WITNESS_VALID. No arithmetic refactor changes the dedicated cleanup bound, conservative on-time accounting, retained loss claims or resume watermark.

The 32-byte report stays in its existing poll owner and is live through the same callbacks. No pointer escapes, no driver receives a new buffer, and no out-of-line phase may reuse report storage while its content is still required. Added caller/callee nesting is a stack cost, not a free lifetime reduction.
