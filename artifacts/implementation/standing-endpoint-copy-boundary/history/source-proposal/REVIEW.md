# Source review

This is a bounded source proposal, not a build result. Its baseline is the exact 36-file current C project in sealed `standing-endpoint-lto`, identical to the fit parent's current C source. The complete LTO, fit and attribution file indices were revalidated before copying. The new candidate retains every baseline byte under `originals/project/`.

## Encoded copies

For an eight-byte sequence `b`, the existing big-endian `r64` computes `sum(b[i] * 256^(7-i))` using unsigned 64-bit arithmetic. `w64` writes exactly that value's eight base-256 digits. Thus `w64(destination,r64(source))` reproduces those eight source bytes for every bit pattern, including zero, high-bit values and `UINT64_MAX`. No narrowing time domain or arithmetic assumption is involved.

Each replacement uses `memmove(destination,source,8)`. The original completes the source read before any destination write; `memmove` has the same as-if temporary snapshot property even if the eight-byte ranges overlap. Its pointer expressions have no side effects and remain in the same full expression. No callback or validation lies inside any replaced expression.

This is a local equivalence claim. Surrounding writes and evaluation order remain exactly as before. In particular, OPEN has already cleared/committed several structures before its lease copy; RESUME updates output state before copying the retained quiescence tick. These changes do not make the entire handler accept arbitrary caller buffer aliasing, and do not move a snapshot before earlier writes. Inputs and state are non-volatile arrays with the existing serialized callback/ownership contract. Concurrent mutation was not supported by the original code either.

| Baseline standing.c line | Copy destination | Eight-byte source | Preserved boundary |
| --- | --- | --- | --- |
| 232 | `bytes + ST_LEASE` | `p + 112` | OPEN's existing post-validation commit |
| 321 | `bytes + ST_LEASE` | `p + 52` | Accepted RENEW after mutation body/revision commit |
| 327 | `work + WORK_TRANSITION` | `bytes + ST_QUIET_AT` | RESUME before clearing prior witness/quiet time |
| 337 | `bytes + ST_LEASE` | `p + 52` | RESUME after continuity transfer |
| 648 | `record + 4` | `report + 20` | Ordinary handoff after every report/account/freshness check |
| 649 | `work + WORK_TRANSITION` | `report + 20` | Same actual handoff, before output/baseline updates |
| 682 | `bytes + ST_QUIET_AT` | `report + 20` | Validated loss handoff, before state becomes 3 |

The callback-local report remains alive throughout each copy. In the existing layout it is separate from retained record/work/controller storage; `memmove` does not require that separation for its own correctness. The RESUME source remains available until the later absent fill. No copied temporary storage or retained field is added.

## Constant absent values

`ABSENT` is exactly `UINT64_MAX`. On this existing `uint8_t`/`uint64_t` profile, its wire encoding is eight `0xff` bytes. Only writes with that literal semantic value become `memset(destination,0xff,8)`.

The twelve baseline sites are: clock-unqualified first-loss timestamps at line 115 (two); OPEN loss time at 233, cleanup/quiet at 234 (two), feedback deadline at 236; RESUME feedback deadline at 328, loss/cleanup/quiet at 338 (three); page-0 unqualified-quiescence redaction at 484; pending feedback-record timestamp at 633. Adjacent fields, write order and the wire redaction predicate remain unchanged. The pending loss handoff alias is still not published as quiescence.

All native-time serializers, reads for validation, arithmetic, counter checks, cutoff comparisons and report predicates remain. In particular, actual handoff plus feedback window at line 651 is still 64-bit addition through `w64`, and `dispatch_report` has its unchanged signature, arguments and checks. No serializers elsewhere are changed. Neither `memmove` nor `memset` guarantees a flash saving: their generated code and any added library body must be counted later.

## Finite service boundary

The attribution packet observed 83 local bytes plus 18 saved register bytes allocated by `hms_endpoint_poll` before its standing-service call and released only afterwards. Source-level sibling branches did not stop GCC from inlining the finite service. This proposal annotates only the existing `poll_finite` definition with `__attribute__((noinline))` when `__GNUC__` is defined. It keeps a no-op macro for other compilers, then undefines the private macro after that function. No portable-source compiler rejection, public ABI, call ordering or branch predicate is introduced.

The retained GCC options documentation at lines 217–222 explicitly describes the function `noinline` exemption. The reviewed qualification profile is the pinned AVR GCC 7.3 / `-Os` / LTO profile; a compiler merely defining `__GNUC__` is not thereby qualified. Other compilers remain source-compatible but have no claimed stack boundary. Existing `-fno-optimize-sibling-calls` and all root/target/storage policies remain proposed unchanged. There is no blanket noinline flag or new forced function root.

The attribute is not a combined stack proof. A later generated-code gate must establish an out-of-line finite service and verify that the standing branch does not carry the finite report/limits allocation. Clones, wrapper saves, call arguments, helper/library frames, callbacks, ISR interruption and startup paths still count. Pre-LTO `.su` files cannot establish the final linked stack. A smaller map or an unlinked backend assembly file cannot establish runtime fit.

Only the three files named in README change. WIRE, literals/vectors, target, fixture, driver integration, root policy, 64-bit domain, authority and loss/ACK/resume behavior are retained byte-for-byte outside the explicit substitutions. [CONTROLS.md](CONTROLS.md) describes the new behavioral control and later evidence requirements.
