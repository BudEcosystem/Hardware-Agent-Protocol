# Proposed controls and generated-code gates

No controls have been compiled or run in this lane. `encoded_time_boundaries` is a new full-controller case, bringing the source list from 13 to 14. It uses the actual common endpoint entry points, fixture clock/driver, lifecycle and retained state. Its literal byte oracles are independent of the C encoder/decoder helpers.

The two bases are `0x81234567fffffff8` and `0xffffffffffffefff`. The first has bit 63 set and carries across the low 32 bits during normal service. The second exercises near-maximum representable time while leaving every installed lease/cleanup/window inside the existing 64-bit domain. Neither changes the installed 60,000-ms maximum lease.

| Event | Relative tick | Expected effect/evidence |
| --- | ---: | --- |
| OPEN, lease `base + 1000` | 0 | Exact retained/wire lease; absent loss, cleanup, quiet and feedback times |
| Prepared acquisitions; START | 0, 1, 2 | Original source sequence and fresh-input authority |
| Active acquisitions and ON handoff | 12, 13, 14 | Activation 1; exact retained actual time; absent pending feedback time; deadline 64 |
| Invalid absent lease, then RENEW to `base + 2000` | 14 | Refusal preserves revision/lease; accepted renewal and duplicate preserve one effect |
| SUSPEND | 14 | First-loss time retained; ownership remains 3 |
| Loss output | 15 | Exact private handoff time; STATUS still emits eight `0xff` quiet bytes |
| Aggregate witness | 16 | SUSPENDED, exact witness tick, two milliseconds conservatively charged |
| ACK and RESUME, lease `base + 3000` | 16 | Old record settles; previous witness copied to transition before witness fields clear |
| New prepared acquisitions and START | 17, 18, 19 | Fresh post-resume observations required |
| Next activation | 29, 30, 31 | Activation 2, ordinary dispatch count 2, loss count 1; ownership retained |

The case also injects clock qualification loss in a fresh ordinary prepared application and requires absent loss/cleanup timestamps, retained claims, FAULT and zero ordinary dispatches. It checks pending-record neighbor fields and confirms wire redaction does not alter the retained private handoff or first-loss tick.

This is not an exhaustive aliasing test or a libc self-test. The seven local copy substitutions are justified by the all-bit-pattern/read-before-write proof in REVIEW. Earlier caller-buffer alias constraints remain. The retained 13 cases cover wire literals/refusals, duplicate mutations, bounded feedback and signed-range direction, ledger pressure, loss witnesses before/equal/after handoff, acquisition cutoff/drift, unknown handoff and interrupted-feedback ACK, finite/standing arbitration and STOP under link backpressure. The original finite suite and integrated runtime controls remain required later as well.

After root source review, a separately reviewed controlled runner must execute the actual native stages with 14 expected standing cases, plain and ASan/UBSan, preserving all prior regressions and exact inputs. No assertion count is claimed before that run. The AVR stage must keep the current LTO profile, 29 function roots plus `main`, nine exact storage objects, warnings, physical/application bounds and reservations. Keep any failed link and every saved backend artifact.

The generated-code review must inspect the actual `hms_endpoint_poll` and finite callee (including any compiler-created variants), establish that the finite report/limits frame is not allocated on the standing branch, and count new copy/fill library calls. If linking succeeds, use the final linked disassembly/symbol map and a complete foreground/callback/helper/ISR stack graph. If linking fails, backend observations remain partial and cannot qualify combined stack or target fit. Recheck USART/interrupt sequence constraints on the resulting image; prior generated evidence does not automatically transfer to new code generation.
