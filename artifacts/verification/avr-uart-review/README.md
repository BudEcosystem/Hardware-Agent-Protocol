# Independent AVR UART receive review

Result: no blocking production finding within the declared receive-only, exclusive USART0, single-foreground-owner contract. Reviewed 2026-11-06 against the frozen producer receipt SHA-256 `2b5b5d36bd897d91b8d94055136a887302363ef075a08eaeebdb0fabc4654874`. This review changed no production source, shared documentation, or EDHOC evidence.

[review.json](review.json) records the source and artifact pins, manual conclusions and limitations. [probe-review.json](probe-review.json) contains the independent host results and exact commands. Copies of the reviewed original inputs are under `inputs/`; deliberately broken copies are under `mutations/`. Those mutation files are regression examples, not candidate implementations.

## Independent checks performed

The reviewer read the complete `avr_uart.c`, `avr_uart.h`, `avr_uart_probe.c`, `check_avr_uart.py`, and existing frame parser/header. The final producer script was reread after its CFG/inlining correction. The frozen AVR disassembly was manually traced for init, receive, discontinuity, frame_step and parser reset. Producer result/size/stack records were inspected as evidence; their AVR ELF was not executed. The two archived official datasheet excerpts, original LF ranges 9910–10160 and 10440–10695, were read completely. This is selected manual coverage, not a complete or current-device-errata review.

The independent probe uses the production C with original host register callbacks and GNU linker wrapping around `hms_frame_reset`. It passed **13,418 checks per variant** in GCC `-O2` and `-O1` AddressSanitizer/UndefinedBehaviorSanitizer builds. It checks all 256 receive-status patterns, all 256 saved-mask patterns, 373 reset observations, and three completed-frame boundary cases. The reset wrapper verifies that the foreground owner, closed loss gate and masked interrupt state remain established before and after the real parser reset. This adds direct observation of the reset/publication boundary to the producer's broader queue and fault tests.

Five intentionally broken source copies were compiled only as host programs and rejected by the independent oracle:

| Mutation | Observed rejection |
| --- | --- |
| Clear the loss gate before resetting the parser | The reset wrapper sees the gate already open. |
| Omit the post-feed loss check | A loss observed during feed leaks a frame result instead of returning LOSS/NONE. |
| Revoke READY after the final masked check and restore | A later loss incorrectly suppresses a frame already linearized as complete. |
| Restore with the interrupt-enable bit forced on | The restored mask differs from the saved mask. |
| Read UDR without requiring captured RXC | A no-data status incorrectly triggers a data-register read. |

These tests distinguish concrete regressions; they are not an exhaustive proof of all possible interleavings, compiler behavior or silicon behavior. The host callbacks are a semantic scheduling model, not an AVR emulator. No target, peripheral, uploader, controller or acquired implementation ran. The independent reviewer did not rerun the producer's AVR compiler/build or modify its artifact directory.

## Source and emitted-instruction conclusions

| Boundary | Independent conclusion |
| --- | --- |
| Status before data | `receive` captures UCSR0A, tests RXC in that captured byte, then reads UDR0 once. The frozen instructions are `lds r25, 0x00C0` at `0xe0`, RXC `sbrs r25, 7` at `0xe4`, and `lds r18, 0x00C6` at `0xe8`. FE/DOR/UPE are mapped from the saved `r25`, not a later FIFO status. |
| Error and overflow loss | FE, DOR, UPE or a clean arrival into a full 16-byte software queue closes the gate and discards the queue. The first trigger byte/status stays intact, while later error reasons accumulate. Gated arrivals still drain one hardware byte and do not enter the parser. DOR and software overflow are reasons, not exact counts of lost bytes or frames. |
| Queue bounds | Valid initialized state and exclusive access keep head/tail modulo 16 and count in 0–16. Status and byte are copied together under the same mask. The fixed queue occupies 41 bytes on the inspected AVR ABI. This is not a whole-application memory reservation. |
| Saved interrupt state | The receive snapshot remains in `r19` from `0xb6` through the common SREG restore at `0xd8`; init uses unchanged `r24`, discontinuity unchanged `r25`. Foreground uses the preserved `r11` snapshot, restores before parser feed, then takes a new snapshot for the final check. No unconditional `sei` appears in the adapter. An entry with I=0 retains I=0. |
| Parser reset and gate reopen | Both loss paths converge on `hms_frame_reset` at `0x222`. Only after it returns do `0x226`/`0x228` clear loss/trigger-valid, followed by clearing foreground ownership and restoring SREG at `0x22c`. New loss after that restore remains pending for the next call. The independent wrapper directly exercises this ordering in host builds. |
| READY suppression and ordering | Queue dequeue is masked; parser feed at `0x272` occurs after the caller's mask is restored at `0x26a`. The second CLI at `0x278` protects the final loss test at `0x27a`/`0x27e`. Only its clean branch publishes the result at `0x2a0`/`0x2a2`. Loss observed during feed yields LOSS/NONE; loss after final restore at `0x2a6` is ordered after the completed frame and handled next. |
| Reentrancy | Producer reentry and foreground reentry latch loss. Foreground reentry returns BUSY without feeding/resetting the active parser or clearing the outer ownership flag. The outer call detects that loss. Init, lifetime, object aliasing and multiple foreground owners remain excluded by contract. |
| Parser scope | Reset clears only parser assembly length/flags, leaving raw storage and all endpoint/application state untouched. After LOSS, raw bytes are not an eligible frame. CRC validates framing corruption, not authentication, authority, freshness or effect completion. |

The source has no receive busy-wait, allocation, transport setup, TX or clock. Each call handles at most one receive-register byte or one foreground byte. The producer's final checker correctly handles inlined helpers and backward jumps to shared epilogues using cycle detection rather than treating every backward branch as a loop. Its local CFG longest paths exclude called parser work and ISR wrappers. Its mask analysis recognizes SREG restore instructions, but does not prove the restored register's value; the manual trace supplies selected data-flow inspection for these exact bytes, not a general formal proof.

The full saved-register byte in the host model is not a promise that a C function preserves caller arithmetic flags. Generated argument checks and arithmetic can change those flags before snapshots or after a restore. The relevant interrupt-enable contract is preserved in the inspected paths.

## Remaining installation obligations

The module assumes an exclusively owned, correctly configured eight-data-bit asynchronous USART0 and an installed RX ISR that calls it. It neither validates nor configures baud, parity, stop bits, MPCM, RX enable, pins or vector setup. A 9-bit link is unsupported. `init` and software discontinuity do not flush the hardware FIFO. Link/configuration transitions need a commissioned hardware-buffer and session policy; reporting a software discontinuity alone is not a physical flush or a new authenticated endpoint session.

One-byte bounded work does not prove that the ISR can service the actual arrival rate. The caller must qualify oscillator/baud tolerance, maximum masking and ISR latency, service fairness, stack/nesting, absolute receive deadlines, persistent overflow/flood behavior, and independent stop/watchdog timing. Returning to an already-disabled interrupt state deliberately leaves CRC execution masked; the caller owns that latency. Neither compiler stack estimates nor the isolated probe's flash/SRAM totals prove a deployed firmware fits or meets timing.

The foreground caller must consume READY synchronously before the next feed and must respect distinct, valid rx/parser/output objects. The callback model is single-threaded and injects selected interrupt-like schedules; it is not evidence for multicore or C-thread access. Loss does not erase boot/session identity, operation records, fences, receipts, cancellation state or uncertain effects. Those semantics require separate integration.

To reproduce the independent **host-only** checks against the same still-valid producer inputs:

```sh
python3 artifacts/verification/avr-uart-review/run_review.py
```

This regenerates host binaries and probe evidence in this directory and verifies the producer's existing source/output hashes before and after. It does not execute the AVR ELF. A changed producer receipt requires a new independent review; regenerating files alone does not renew the manual conclusions in `review.json`.
