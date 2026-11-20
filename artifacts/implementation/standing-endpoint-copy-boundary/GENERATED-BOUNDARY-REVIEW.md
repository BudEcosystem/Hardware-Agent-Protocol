# Generated finite/standing call boundary

The retained failed-link LTRANS assembly now separates the finite frame from the standing call path. This is a backend-code observation for this exact unsuccessful AVR link, not a final linked-image, combined-stack or runtime-fit qualification.

The complete `hms_endpoint_poll` definition was read at raw assembly lines 23858–23951, and the complete out-of-line `poll_finite` definition at 9820–11589, in `build/avr/compiler-tmp/ccnmby5y.ltrans0.ltrans.s`. Input hashes, inclusive line ranges, range hashes and complete instruction/call observations are in [boundary-coverage.json](boundary-coverage.json). The frozen endpoint source lines 528–614 were also read completely.

`hms_endpoint_poll` pushes only `r14,r15,r16,r17,r28,r29` at lines 23863–23883. It has no local-frame allocation, stack-pointer register adjustment or outgoing argument pushes. After its unchanged early checks it calls `update` at 23910, then selects the standing branch using the non-null attachment and slot value 2. The standing call at 23922 returns directly to the common six-pop/`ret` epilogue at 23929–23937. The alternate branch calls `poll_finite` at 23944 and jumps to that same epilogue. There is no path from the standing return through finite service, and no finite report/limits allocation before the standing call.

The separate `poll_finite` body pushes 18 saved register bytes at 9825–9893 and allocates 82 local bytes at 9901–9909. Its common epilogue at 9963–9988 restores those 82 bytes and pops the 18 saved registers. Four additional outgoing argument bytes are pushed at 10649–10654 before its installed-driver `icall` at 10663. They remain until the four pops at 10682–10685, including the intervening clock/cutoff checks. These finite-only allocations are inside the callee. The existing interrupt-preserving stack-pointer update sequence remains visible; no timing or whole-ISR analysis was performed here.

| Failed-link local evidence | Parent LTO wrapper | Current wrapper | Current finite callee |
| --- | ---: | ---: | ---: |
| Local frame bytes | 83 | 0 | 82 |
| Saved register bytes | 18 | 6 | 18 |
| Maximum explicit outgoing argument bytes | 4 | 0 | 4 |
| Backend `.su` entry | 107, dynamic/bounded | 8, static | 106, dynamic/bounded |
| Map section bytes | 2,874 | 86 | 2,806 |

The parent standing call at raw line 22299 retained its wrapper's 83-byte local frame plus 18 saved bytes. The current standing call retains six saved bytes: a 95-byte reduction in this caller-owned live allocation alone. Both calls still have ordinary call return-address costs and all standing/helper/callback/ISR frames. The finite path now includes an additional wrapper/callee boundary. Therefore this observation does not establish a 95-byte reduction in the application's maximum stack, or any combined bound.

The current two sections total 2,892 bytes, 18 bytes more than the parent's combined wrapper section. Independent text instruction-width sums agree with the failed maps: current wrapper 40 instructions / 86 bytes and finite callee 1,354 instructions / 2,806 bytes. In these units only `call` is four bytes; all other observed instructions are two bytes, and neither unit contains inline data. The parent total and full-unit review are retained in the sealed [finite attribution](../../verification/standing-lto-attribution/FINITE-ATTRIBUTION.md); this review reread its prologue/standing-call/epilogue window at lines 22169–22365 rather than claiming a second complete parent-unit review.

The backend `.su` values are consistent with the inspected local allocations and ATmega328P two-byte incoming return address: wrapper `6 + 2 = 8`, finite `82 + 18 + 4 + 2 = 106`. They are not transitive stack totals. The complete linked callback/helper/ISR graph, actual final image and repeat UART instruction review remain absent because the physical flash link failed. No old or pre-LTO stack bound is transferred to this build.

This review ran only retained-text reads, hashing and standard-library data extraction. It invoked no compiler, `nm`, `objdump`, candidate import, probe, native test, emulator or target code, and changed no pinned source, runner, receipt or build artifact. Overall map/resource arithmetic, process audit and results are retained separately by the parent reviewer.
