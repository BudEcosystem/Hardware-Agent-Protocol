# Future verification boundary

No tests or candidate were executed for this proposal. The data reader only parses retained text/bytes. A future implementation must preserve the existing finite, runtime, standing and differential controls; new counts are observed results, not invented in advance.

The sealed baseline provides kernel 3 cases/13,014 assertions in both modes; standing 14/766; finite 26/2,548 plus malformed/pipe controls; runtime 11/143,471 plus malformed/256 bounds; and differential 16 groups/1,241 assertions. Its four traces agree on 829 state records and SHA `086bc3496901dc560e4aef0f51abb426e5d90698d27920ca57a27dd1a3e85541`. Preserve all old control bodies and retain the old candidate as the independent scalar baseline for new differential traces.

## Arithmetic and representation controls

- Compare candidate byte operations against the unchanged scalar uint64 baseline over all positions of the highest differing byte, equality, zero, UINT64_MAX, high-bit bases and mixed encoded/native representations. Include all 256 digit values around borrow/carry transitions, with deterministic multi-byte patterns. This is bounded testing plus the digit proof, not an exhaustive 2^128 enumeration.
- Exercise full-width subtraction with and without final borrow. For bounds 0, 1, 60,000, INT32_MAX and UINT32_MAX, cover elapsed bound-1/equal/+1 where representable, high-bit end/start and wraparound cases. In particular, equal low32 with different high32 must not compare equal to a uint32 bound.
- Exercise M-delta-1, M-delta and M-delta+1 for every permitted delta width, and distinguish strict cutoff saturation from schedule rejection. Check minimum-cutoff ties and already earlier cutoffs.
- Test accounting at remaining-1/equal/+1 and total/max_on boundaries, including output already off. Verify the existing commit-before-false behavior and unchanged state on earlier failures.
- Check native byte orientation with full non-palindromic patterns, then compare native/native, native/encoded and encoded/encoded results. Select the intended byte backend in the native build; passing only the scalar fallback does not qualify the new implementation. Preserve compiler portability/fallback source checks without executing an unreviewed second compiler.
- For every changed writer, use deliberate partially overlapping source/destination buffers and high-bit/carry inputs. Check the exact final bytes against the old read-before-write snapshot semantics, not merely a non-overlapping happy path. Retain unchanged serializer alias tests/evidence.

## Full-controller phase traces

Continue plain and sanitized candidate-versus-baseline comparisons with complete response/state/effect traces and callback argument bytes. Add only controls needed by the new phase boundaries:

1. Finite admission with metadata or guard callbacks modifying the original request timestamp bytes after their captures, including a request backed by state that later changes. Confirm exact old status, captured timing, claims/fences and callback sequence. Retain the existing high-bit ARM, latest/lease/horizon/sentinel and precedence scenarios; do not manufacture an unreachable late branch by mutating callback-owned internals.
2. Standing reports whose captured sequence/acquired/value differ only at high timestamp bytes; older/equal/new acquisition; duplicate sequence with changed contents; wrong quality/epoch/range simultaneously with stale timing. Confirm original first error and unchanged acceptance state where appropriate.
3. Ordinary transition with clock/epoch drift at guard and handoff, deadline before/equal/after, saturation at the top of the full domain, actual dispatch later than the pre-driver snapshot, and driver timeout/dispute. Match activation identity, effect count and possible-effect/unknown evidence.
4. Loss witness acquired before/equal/after actual loss handoff, cleanup cutoff boundaries, counter/elapsed overflow after witness fields have been copied, and ACK before/after valid quiescence. Compare partial state as well as final responses; an all-or-nothing rewrite must fail this oracle.
5. Concurrently eligible finite and standing resource claims, retained claims through loss/resume, output on-time exhaustion and pending feedback. No host OP loop or simplified lifecycle substitutes for the standing controller.

Trace equality is evidence for these chosen executions, not universal semantic proof. Every new helper call/write order also needs source review against the unchanged baseline. Any callback fixture modification must be retained separately and compiled identically into both sides so it cannot hide a candidate-specific effect.

## Build, resource and whole-image gates

Reuse the reviewed bounded owned runner model with its exact native/AVR tool/plugin/owner pins, warnings, caps, process cleanup and immutable attempts. Include new private units in every finite/runtime/standing/differential/AVR link path. Retain the same -Os/-flto profile, all roots/storage and original device. Do not run until the source and runner are reviewed.

Report the complete map, not sum-of-helper changes: flash against 39,902 and the 32,256 application allowance; static against 1,503; all nine storage sizes; all 29+main roots; aliases, clones, library bodies and any tables. Compare emitted callers and helpers together. Source reductions and compiler IR units are not flash savings.

Inspect generated byte loops for full eight-digit processing, safe bounded accesses and selected native layout. Inspect actual phase boundaries and caller/outgoing/save frames. Derive the combined foreground/callback/ISR path only from a valid final image and complete reachable graph; per-unit or isolated backend `.su` records do not prove stack fit. A smaller failed map remains unsupported, and a valid link alone is not physical I/O qualification.
