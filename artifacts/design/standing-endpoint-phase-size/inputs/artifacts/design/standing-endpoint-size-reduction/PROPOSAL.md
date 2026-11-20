# Concrete refactor proposal

Prepare one isolated successor to the sealed copy-boundary candidate after source-scope review. The objective is to replace repeated private numeric/wire work across both endpoint protocols, then constrain the high-pressure phase boundaries. Keep the existing public headers, layouts and callable signatures, including driver callbacks and `dispatch_report`; keep complete uint64 arithmetic, wire bytes/error precedence, all 29 retained function roots plus `main`, and all nine charged storage roots. No new static scratch buffer, table, descriptor array or state is available within the exact 160-byte delta. No implementation or runner is included in this design packet.

## 1. Shared private wire operations, across both handlers

Create a private implementation unit/header; it is not another public protocol API. Use a conditional GCC qualification attribute for deliberately shared leaves. Other compilers remain source-compatible and unqualified until their generated code is checked. Do not assume `noinline` prevents cloning or guarantees sharing; inspect final allocations and calls.

The following source groups are identical in meaning and order and should have one implementation:

| Private operation | Existing call sites | Required exact sequence |
|---|---|---|
| Write 38-byte context identity | finite `write_hello`338–346, `write_control`348–354; standing `describe`406–423 page1 | control generation4, context handle2, context digest32. Keep each field read and write in that order. |
| Write 21-byte finite clock/highwater/claim tail | HELLO at133 and control at48 | now8, armed-until8, call highwater4, held mask1, same order. |
| Write one native uint64 snapshot | finite receipt/HELLO/control; standing DESCRIBE/NEXT/transition timestamps | Snapshot the pointed-to native value at exactly the former by-value argument evaluation point; encode the same eight bytes, in the same write order. Keep original writer ABI if other call sites use it. |
| Commit accepted observation bytes | standing `accept_observation`545–547 | Four copies in current order, then quality/continuity/pending/reserved; apply the channel-specific flag after the shared commit. No validation is moved into the commit helper. |

HELLO's constant callbacks still finish before context serialization. Standing DESCRIBE still invokes both epoch callbacks at their existing positions before the following highwater/fence stores. Do not cache the entire endpoint into a new snapshot or move writes across callbacks. Sharing a field group is not permission to memcpy a native struct, merge v1/v2 response formats, change padding, or assume an undocumented non-overlap property. Each helper must preserve the original read-before-write behavior, including source snapshots for scalar writers.

Unify the two decoder implementations through this private unit only as a subordinate cleanup; its identified 82-byte duplicate body is not the main fit strategy. The existing `w64` and `put64` are already aliased, so merely unifying those names is not a new saving.

## 2. One full-width private time kernel, used by all three large paths

The main change should centralize **complete repeated expressions**, not add an out-of-line wrapper around every scalar load. Keep native snapshots where the original code captures them; pass their addresses internally to avoid repeating eight-byte arguments/returns when callers need only a predicate. Encoded arrays stay encoded; their published offsets and byte order are unchanged. Proposed private operations are:

1. Compare an existing native uint64 snapshot to an encoded eight-byte value, returning the three-way result. Callers retain the exact `<`, `<=`, `==`, `>=` tests and ABSENT policy.
2. Compare two captured native values or native/encoded values after unsigned subtraction against a uint16/uint32 bound. Keep a separate ordering check wherever the old expression has one; return the same strict or inclusive predicate. Do not silently replace modulo subtraction with signed arithmetic or collapse error-producing checks.
3. Update an existing native cutoff with `min(cutoff, base < UINT64_MAX-delta ? base+delta : UINT64_MAX)`, where `base` is encoded and `delta` has its original width. This exact leaf can serve the two observation ages and on-time allowance in `dispatch_cutoff`; keep all surrounding early returns and accounting checks.
4. Encode a checked native-plus-small-delta result at the same commit point. The caller retains its exact overflow inequality and loss decision. This is not saturation unless the original expression saturates.

Implement the first version in portable C using exact unsigned64 semantics inside these shared leaves. New helper signatures are private only; all existing signatures and driver arguments stay unchanged. This can localize compiler marshalling without changing representation. If it still expands into large wide-value setup, the next reviewed implementation boundary is a canonical eight-byte arithmetic kernel using bounded byte loops and explicit carry/borrow, not a narrower clock. Its proof must establish base-256 equivalence for all 2^64 bit patterns and preserve ABSENT separately. Do not ship both alternative kernels or an interpreter, and do not undertake the byte-loop alternative merely on intuition without the first generated result.

Concrete migration groups, each preserving statement and short-circuit order:

| Group | Source boundaries and capture requirements |
|---|---|
| Standing freshness and schedule | `fresh`88–95, `lease_valid`156–159, `synchronize`131–142; poll phase gates734–747. Preserve freshness `< age` and expiry `>= deadline`. |
| Observation acceptance | 521–548. `sequence`, `acquired` and `value` remain captured at entry; equal sequence/conflicting contents remains a distinct refusal. Older acquisition check precedes elapsed-age refusal exactly as now. |
| Feedback/ordinary dispatch | 558–666. Preserve strict post-command observation timing, all pending/sequence tests, saturated cutoff minima, record identity before driver entry, and actual-dispatch accounting afterward. `before` remains the pre-driver snapshot and fresh `now_tick` remains post-driver. |
| Loss service | 667–715. Preserve cleanup expiry, first-loss time, private handoff-time alias, strictly later witness, unresolved/disputed behavior, conservative accounting through confirmed quiescence and witness publication last. |
| Finite admission/arm | `arm_context`254–265 and `admit`269–336. **Keep nb/latest/complete/lease snapshots captured before `describe`**, and use those same captured values after guard/clock callbacks. Do not reload the request to reduce stack. Preserve failure priority, ownership commit and fence advancement. |
| Finite continued service | `update`100–142, `cutoff_reason`517–527 and existing `poll_finite`537–593 use the same private predicates where exact expressions match. Preserve the selected loss reason and callback boundaries; keep finite completion and standing feedback distinct. |

This is a coordinated internal refactor spanning the full numeric paths rather than another observation-copy-only increment. Exact unchanged old expressions should appear beside each replacement in its review diff, with capture and failure-order notes. The kernel is not allowed to call a clock, metadata provider, guard or driver, or mutate authority/state.

## 3. Deliberate phase boundaries after shared operations are in place

Use generated liveness evidence to keep these specific source phases separate when their measured result is beneficial. Do not apply blanket noinline to all existing helpers.

- Standing poll: pure accepted-observation commit; loss service; active feedback; ordinary evaluate/transition. Retain the single 32-byte report in its original owner and pass it to the selected phase; do not duplicate it or reuse report storage while a callback can see it. The outer poll performs the same synchronization, guard, phase selection and at most one driver service.
- Standing handling: OPEN validation/commit; mutation validation/commit; response selection/serialization. Leave `syntax`, request identity/revision checks, refresh/synchronize calls and response counter order where they are. OPEN's single ownership commit and RESUME's retained evidence watermark must not be split by a callback.
- Finite handling: an early routing wrapper and an explicit finite-only handling function; within the finite path keep admission and response serialization as separate phases. The current 81-byte caller-owned frame on the v2 route is an actual target for frame separation. Its removal from that call path is not presumed flash savings.

These boundaries are not duplicate engines to delete. Most were called once before inlining. Additional calls/save areas can outweigh reduced frame-address work. Qualify the generated boundary and charge the full maximum caller+callee+outgoing+interrupt path, not just each `.su` local figure. Preserve the already reviewed `poll_finite` boundary.

## Measurement gates and full-gap decision

The future source increment should include shared serialization and full-width predicates across **both handlers and standing poll**, plus the smallest deliberate phase boundaries required for those helpers to remain shared. Retain source revisions for attribution, then run the bounded native/LTO stages only after their source and runner are reviewed. Compare the **combined** map effect; do not manufacture per-edit savings from one build.

Every report must include the remaining physical and application gap, new helper/library sections, every root and storage object, generated calls/clones, native effect/response equivalence and the full stack-evidence status. A reduction that still overflows remains unsupported fit. If the compiled private kernel and phase structure do not materially address the gap, stop presenting micro-edits as a path to 328P qualification. Review the byte-loop numeric implementation as the next larger internal boundary, or retain an explicit unsupported-fit outcome for this exact profile. No measured data here justifies promising that either approach will remove all 9,042 bytes.

A smaller image alone cannot qualify the device. The target remains ATmega328P/16MHz/2KiB SRAM, all boot/clock/NVM/UART/stop/loss services and roots remain, the application allowance remains 32,256, and no existing reserve is removed. Complete final stack/callback/ISR accounting and physical driver qualification remain separate gates after a valid link.
